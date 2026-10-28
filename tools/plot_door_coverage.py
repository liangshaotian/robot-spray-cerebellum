"""Export reproducible relative-dose maps; these are not physical film thickness."""
import pathlib,json,argparse
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from spray_cerebellum.common import REPO,read_json,atomic_json
from spray_cerebellum.models import TaskRequest
from spray_cerebellum.planning import plan_surface

class Context:
    def check(self):pass

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output-dir',type=pathlib.Path,default=REPO/'.local/precise_demo_report')
    args=parser.parse_args()
    folder=REPO/'.local/assets/artec_e350_door_v2';manifest=read_json(folder/'manifest.json')
    destination=args.output_dir;destination.mkdir(parents=True,exist_ok=True)
    with np.load(folder/'surface.npz') as surface:u=surface['u'];v=surface['v']
    fig,axes=plt.subplots(1,2,figsize=(13,5),layout='constrained');report={}
    for axis,method in zip(axes,('raster','sac')):
        task=TaskRequest.model_validate({'task_id':'comparison-'+method,'planning':{'method':method,'policy_id':manifest['policy_id']}})
        plan=plan_surface(task,manifest,folder,manifest['allowed_roi'],Context());q=plan['quality'];report[method]=q
        image=axis.imshow(np.ma.masked_where(~plan['coating_mask'],plan['relative_dose']),origin='lower',
            extent=[u[0],u[-1],v[0],v[-1]],cmap='turbo',vmin=0,vmax=4,aspect='equal')
        for segment in sorted({p['segment'] for p in plan['history']}):
            row=[p for p in plan['history'] if p['segment']==segment]
            axis.plot([p['u'] for p in row],[p['v'] for p in row],color='white',linewidth=.6,alpha=.8)
        axis.set(xlabel='Vehicle length u (mm)',ylabel='Height v (mm)',xlim=(-960,170),ylim=(80,770),
            title=f"{method.upper()} | coverage {q['coverage_fraction']:.1%} | dose CV {q['relative_dose_cv']:.1%}")
        axis.set_facecolor('#dce2e8')
    fig.colorbar(image,ax=axes,label='Relative deposited dose (uncalibrated)')
    fig.suptitle('Same front-door target and spray settings | white lines: surface paths\nMasked handle and panel boundary; no physical film-thickness claim',fontsize=11)
    fig.savefig(destination/'relative_dose_comparison.png',dpi=160)
    atomic_json(destination/'planning_comparison.json',report)
    print('EXPORTED',json.dumps(report))

if __name__=='__main__':main()
