"""Minimal 3MF writer.

Bambu Studio cannot read the viewer's GLBs, and a merged STL would arrive as
one object -- fatal here, because plate 1 mixes 0.12, 0.16 and 0.20 mm parts
and needs per-object layer heights. So each part is written as its own
<object>, positions baked into the vertices, identity transforms in <build>.
That is plain 3MF core: no Bambu extension, no project metadata, just geometry
the slicer can arrange and configure per object.
"""
import zipfile

_CT = ('<?xml version="1.0" encoding="UTF-8"?>\n'
       '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
       '<Default Extension="rels" ContentType="application/vnd.openxmlformats-'
       'package.relationships+xml"/>'
       '<Default Extension="model" ContentType="application/vnd.ms-package.'
       '3dmanufacturing-3dmodel+xml"/></Types>')

_RELS = ('<?xml version="1.0" encoding="UTF-8"?>\n'
         '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/'
         'relationships"><Relationship Target="/3D/3dmodel.model" Id="rel0" '
         'Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>'
         '</Relationships>')


def write(path, items):
    """items: [(name, mesh)], vertices already in plate coordinates."""
    parts = ['<?xml version="1.0" encoding="UTF-8"?>\n<model unit="millimeter" '
             'xml:lang="en-US" xmlns="http://schemas.microsoft.com/'
             '3dmanufacturing/core/2015/02"><resources>']
    for oid, (name, mesh) in enumerate(items, 1):
        V, F = mesh._np()
        parts.append(f'<object id="{oid}" type="model" name="{name}"><mesh><vertices>')
        parts.append("".join(
            '<vertex x="%.4f" y="%.4f" z="%.4f"/>' % (v[0], v[1], v[2]) for v in V))
        parts.append('</vertices><triangles>')
        parts.append("".join(
            '<triangle v1="%d" v2="%d" v3="%d"/>' % (f[0], f[1], f[2]) for f in F))
        parts.append('</triangles></mesh></object>')
    parts.append('</resources><build>')
    for oid in range(1, len(items) + 1):
        parts.append(f'<item objectid="{oid}" '
                     'transform="1 0 0 0 1 0 0 0 1 0 0 0"/>')
    parts.append('</build></model>')
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", _CT)
        z.writestr("_rels/.rels", _RELS)
        z.writestr("3D/3dmodel.model", "".join(parts))
