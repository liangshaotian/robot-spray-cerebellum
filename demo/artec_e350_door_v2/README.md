# E350 front-door demo assets

Car body by **Artec Group Inc. / Artec 3D**: https://www.artec3d.com/3d-models/car-body

The downloaded PLY archive includes a Creative Commons Attribution 3.0 Unported license; the unmodified text is included as `LICENSE.source.txt`.

`car_body_highres_smooth.ply.gz` is the complete, rigidly transformed scan mesh with smooth vertex normals. Vertex/triangle topology and dimensions are retained. `surface.npz` contains mesh-derived panel samples, a smoothed planning support surface, and manually selected door/handle masks. The SAC checkpoint is trained for this asset only. These are not raw sensor points or calibrated paint-film measurements.

Run `python tools/setup_precise_demo.py` from the repository root after editable installation. It verifies `checksums.json`, expands the mesh, and registers the asset under `.local/assets/artec_e350_door_v2`. The setup does not train a policy or download the car model. See `docs/PRECISE_DEMO.md` for reproduction and limits.
