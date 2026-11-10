"""Verify the published real-scan result, without RoboDK, raw scans or training.

This reproduces saved metric calculations, not the reconstruction/search run.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
from pathlib import Path
import numpy as np


def metrics(dose, target, edge, area):
    values=dose[target];weights=area[target]
    assert np.isfinite(values).all() and np.isfinite(weights).all() and (weights>0).all()
    mean=float(np.average(values,weights=weights))
    def average(values,mask):return float(np.average(values[mask],weights=area[mask]))
    return dict(within_20_percent_fraction=average((dose>=.8)&(dose<=1.2),target),
        relative_dose_cv=float(np.sqrt(np.average((values-mean)**2,weights=weights))/mean),
        relative_target_rmse=float(np.sqrt(np.average((values-1)**2,weights=weights))),
        threshold_coverage_fraction=average(dose>=.2,target),edge_threshold_coverage_fraction=average(dose>=.2,edge),
        edge_within_20_percent_fraction=average((dose>=.8)&(dose<=1.2),edge),relative_dose_mean=mean)


def verify(directory: Path):
    record=json.loads((directory/'results.json').read_text(encoding='utf-8'))
    with np.load(directory/'fixed_path_evaluation.npz',allow_pickle=False) as saved:
        data={k:saved[k] for k in saved.files}
    assert 'h' not in data and not any(k in data for k in ('xyz','rgb','points_mm'))
    target=data['target'].astype(bool);edge=data['edge'].astype(bool)
    assert target.any() and edge.any() and not np.any(edge&~target)
    assert target.shape==(len(data['v']),len(data['u']))
    errors={}
    for key,record_key in [('baseline','baseline'),('search','search_two')]:
        calculated=metrics(data[key],target,edge,data['area'])
        error=max(abs(value-record[record_key][k]) for k,value in calculated.items())
        assert error<1e-10,(key,error);errors[key]=error
    for filename,expected in record['figures_sha256'].items():
        assert hashlib.sha256((directory/filename).read_bytes()).hexdigest()==expected,filename
    with (directory/'search_path_workpiece.csv').open(encoding='utf-8-sig',newline='') as f:rows=list(csv.DictReader(f))
    assert len(rows)==record['trajectory_anchors']
    starts=sum(row['spray_segment_start']=='True' for row in rows)
    assert starts==record['spray_strokes']
    speeds=np.array([float(row['speed_assumed_mm_s']) for row in rows])
    assert speeds.min()>=350-1e-8 and speeds.max()<=450+1e-8
    assert np.max(abs(np.diff(np.r_[400.,speeds])))<=6+1e-8
    surf=np.array([[float(row['surface_'+a+'_native']) for a in 'xyz'] for row in rows])
    tcp=np.array([[float(row['tcp_'+a+'_native']) for a in 'xyz'] for row in rows])
    normal=np.array([[float(row['normal_'+a]) for a in 'xyz'] for row in rows])
    assert np.max(abs(np.linalg.norm(normal,axis=1)-1))<1e-8
    assert np.max(np.linalg.norm(tcp-surf-200*normal,axis=1))<1e-8
    quality=json.loads((directory/'data_quality.json').read_text(encoding='utf-8'))
    assert quality['readable_scans']==11 and quality['distinct_confirmed_physical_workpieces']==1
    assert not record['physical_film_calibrated'] and not record['robot_ik_collision_validated']
    assert not record['robodk_path_overlay_completed']
    inventory=json.loads((directory/'synthetic_shape_inventory.json').read_text(encoding='utf-8'))
    transfer=json.loads((directory/'synthetic_transfer_summary.json').read_text(encoding='utf-8'))
    with (directory/'synthetic_cases.csv').open(encoding='utf-8-sig',newline='') as f:cases=list(csv.DictReader(f))
    assert inventory['families']==18 and inventory['cases']==len(cases)==54
    assert len({r['asset_id'] for r in cases})==54
    assert {r['family'] for r in cases}=={r['family'] for r in inventory['inventory']}
    for family in inventory['inventory']:
        group=[r for r in cases if r['family']==family['family']]
        assert len(group)==3 and {int(r['variant']) for r in group}=={1,2,3}
        for expected in family['cases']:
            actual=next(r for r in group if r['asset_id']==expected['asset_id'])
            assert json.loads(actual['all_generator_parameters_json'])==expected['parameters']
            assert float(actual['xy_length_mm'])==expected['parameters']['length']
            assert float(actual['xy_width_mm'])==expected['parameters']['width']
        for name,key,field in [('baseline','baseline_target_band','within_20_percent_fraction'),
                               ('search_two','search_target_band','within_20_percent_fraction'),
                               ('baseline','baseline_cv','relative_dose_cv'),('search_two','search_cv','relative_dose_cv')]:
            assert abs(np.mean([float(r[key]) for r in group])-family[name][field])<1e-10
    assert hashlib.sha256((directory/'synthetic_shapes_overview.png').read_bytes()).hexdigest()==inventory['overview_sha256']
    execution=None
    if (directory/'execution_validation_20261110.json').exists():
        execution=json.loads((directory/'execution_validation_20261110.json').read_text(encoding='utf-8'))
        moves=json.loads((directory/'execution_trajectory_20261110.json').read_text(encoding='utf-8'))['moves']
        checks=json.loads((directory/'execution_segment_checks_20261110.json').read_text(encoding='utf-8'))
        assert execution['virtual_cell_only'] and not execution['real_robot_executed']
        assert not execution['scale_confirmed'] and not execution['physical_base_registration']
        assert execution['ik_collision_passed'] and execution['native_simulation_completed']
        assert len(moves)==len(checks)==execution['waypoint_count']==execution['checked_segments']==471
        assert [c['index'] for c in checks]==list(range(471)) and all(c['result']==0 for c in checks)
        assert sum(c['samples'] for c in checks)==execution['accepted_path_collision_samples']==6725
        anchors=[m for m in moves if m['kind']=='entry' or m['spray_on']]
        assert len(anchors)==len(rows)==345
        assert np.max(np.abs(np.array([m['nozzle_xyz_mm'] for m in anchors])-tcp))<1e-8
        for m in moves:
            assert len(m['joints_deg'])==6 and np.isfinite(m['joints_deg']).all()
            rotation=np.array(m['rotation_matrix'])
            assert np.max(np.abs(rotation.T@rotation-np.eye(3)))<1e-8
            if m['spray_on']:assert 350-1e-8<=m['speed_mm_s']<=450+1e-8
        assert len(execution['off_transfer_corrections'])==1
        for correction in execution['off_transfer_corrections']:
            move=moves[correction['index']]
            assert not move['spray_on'] and move['motion']==correction['corrected_motion']=='MoveL'
        independent=execution['independent_checks']
        assert independent['passed'] and independent['all_joint_limits_satisfied']
        assert independent['collision_positive_control'][-1]['colliding_pairs']>0
        assert independent['collision_pairs_before']==independent['collision_pairs_after_restore']==0
        assert independent['maximum_fk_position_error_mm']<.01 and independent['maximum_fk_orientation_error_deg']<.01
        assert hashlib.sha256((directory/execution['figure']).read_bytes()).hexdigest()==execution['figure_sha256']
    return dict(passed=True,metric_max_error=errors,target_cells=int(target.sum()),edge_cells=int(edge.sum()),
        trajectory_anchors=len(rows),spray_strokes=starts,source_scale_confirmed=False,synthetic_shape_families=18,synthetic_cases=54,
        virtual_e12_execution_record_verified=execution is not None,
        scope='Offline verification of saved metrics, geometry constraints and follow-up E12 records; does not rerun search, IK or collisions and is not physical robot validation')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory',type=Path,default=Path(__file__).resolve().parents[1]/'experiments/real_scan_20261109')
    args=parser.parse_args();print(json.dumps(verify(args.directory),ensure_ascii=False,indent=2))


if __name__=='__main__':main()
