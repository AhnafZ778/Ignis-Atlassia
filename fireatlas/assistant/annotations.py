"""Annotation geometry is data, never executable browser code."""
import math


def validate_geometry(value):
    if not isinstance(value,dict) or value.get("type") not in {"Point","Polygon"}:raise ValueError("Use a geographic point or polygon.")
    coords=value.get("coordinates")
    points=[coords] if value["type"]=="Point" else coords[0] if isinstance(coords,list) and len(coords)==1 else []
    if not points or len(points)>100:raise ValueError("Annotation geometry is too large or invalid.")
    for point in points:
        if not isinstance(point,list) or len(point)!=2 or not all(type(n) in (int,float) and math.isfinite(n) for n in point) or not -180<=point[0]<=180 or not -86<=point[1]<=86:
            raise ValueError("Annotation coordinates must be geographic longitude, latitude.")
    if value["type"]=="Polygon" and (len(points)<4 or points[0]!=points[-1]):raise ValueError("Annotation polygon must be closed.")
    return {"type":value["type"],"coordinates":coords}
