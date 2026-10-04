"""Deterministic geographic selection, including polygon boundary points."""
def contains(ring, x, y):
    inside = False
    for (ax, ay), (bx, by) in zip(ring, ring[1:]):
        cross = (x-ax)*(by-ay)-(y-ay)*(bx-ax)
        if abs(cross) < 1e-10 and min(ax,bx)-1e-10 <= x <= max(ax,bx)+1e-10 and min(ay,by)-1e-10 <= y <= max(ay,by)+1e-10:
            return True
        if (ay>y) != (by>y) and x < (bx-ax)*(y-ay)/(by-ay)+ax:
            inside = not inside
    return inside
