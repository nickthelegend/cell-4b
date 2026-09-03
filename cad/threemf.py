"""Minimal 3MF writer, with multi-material parts.

Bambu Studio cannot read the viewer's GLBs, and a merged STL would arrive as
one object -- fatal for plate 1, which mixes 0.12, 0.16 and 0.20 mm parts and
needs per-object layer heights. So each part is its own printable object.

A part may itself be several VOLUMES with different filaments (the shells:
body in one colour, lettering inlay in another). That is expressed the way
Bambu does it -- each volume is a mesh <object>, the printable thing is an
<object> of <components> pointing at them, and Metadata/model_settings.config
maps each component to a filament index. PrusaSlicer's own Slic3r_PE_model.config is deliberately NOT written: there a
volume is a triangle RANGE into one merged mesh, which is not how this file is
built, so any ids would be invented. A slicer that reads neither still gets
correct geometry, just without the colour split.
"""
import zipfile

_CT = ('<?xml version="1.0" encoding="UTF-8"?>\n'
       '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
       '<Default Extension="rels" ContentType="application/vnd.openxmlformats-'
       'package.relationships+xml"/>'
       '<Default Extension="model" ContentType="application/vnd.ms-package.'
       '3dmanufacturing-3dmodel+xml"/>'
       '<Default Extension="config" ContentType="application/vnd.bambulab.'
       'model.config"/></Types>')

_RELS = ('<?xml version="1.0" encoding="UTF-8"?>\n'
         '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/'
         'relationships"><Relationship Target="/3D/3dmodel.model" Id="rel0" '
         'Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>'
         '</Relationships>')

_IDENT = "1 0 0 0 1 0 0 0 1 0 0 0"


def _mesh_xml(mesh):
    V, F = mesh._np()
    return ('<mesh><vertices>'
            + "".join('<vertex x="%.4f" y="%.4f" z="%.4f"/>' % (v[0], v[1], v[2])
                      for v in V)
            + '</vertices><triangles>'
            + "".join('<triangle v1="%d" v2="%d" v3="%d"/>' % (f[0], f[1], f[2])
                      for f in F)
            + '</triangles></mesh>')


def write(path, items):
    """items: [(name, mesh)] or [(name, [(vol_name, mesh, extruder), ...])].

    Vertices are already in plate coordinates; transforms stay identity.
    """
    norm = []
    for name, body in items:
        if isinstance(body, list):
            norm.append((name, body))
        else:
            norm.append((name, [(name, body, 1)]))

    res, build, cfg = [], [], []
    nid = 1
    for name, vols in norm:
        vol_ids = []
        for vname, mesh, ext in vols:
            res.append(f'<object id="{nid}" type="model" name="{vname}">'
                       + _mesh_xml(mesh) + '</object>')
            vol_ids.append((nid, vname, ext))
            nid += 1
        oid = nid
        nid += 1
        res.append(f'<object id="{oid}" type="model" name="{name}"><components>'
                   + "".join(f'<component objectid="{v}" transform="{_IDENT}"/>'
                             for v, _, _ in vol_ids)
                   + '</components></object>')
        build.append(f'<item objectid="{oid}" transform="{_IDENT}"/>')
        cfg.append(f'<object id="{oid}"><metadata key="name" value="{name}"/>'
                   + "".join(
                       f'<part id="{v}" subtype="normal_part">'
                       f'<metadata key="name" value="{vn}"/>'
                       f'<metadata key="matrix" value="1 0 0 0 0 1 0 0 0 0 1 0 0 0 0 1"/>'
                       f'<metadata key="extruder" value="{e}"/></part>'
                       for v, vn, e in vol_ids)
                   + '</object>')

    model = ('<?xml version="1.0" encoding="UTF-8"?>\n<model unit="millimeter" '
             'xml:lang="en-US" xmlns="http://schemas.microsoft.com/'
             '3dmanufacturing/core/2015/02"><resources>'
             + "".join(res) + '</resources><build>' + "".join(build)
             + '</build></model>')
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", _CT)
        z.writestr("_rels/.rels", _RELS)
        z.writestr("3D/3dmodel.model", model)
        z.writestr("Metadata/model_settings.config",
                   '<?xml version="1.0" encoding="UTF-8"?>\n<config>'
                   + "".join(cfg) + '</config>')
