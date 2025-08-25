import numpy as np

class CentroidTracker:
    def __init__(self, max_disappeared=15):
        self.next_id = 1
        self.objects = {}       # id -> centroid
        self.disappeared = {}   # id -> frames missing
        self.max_disappeared = max_disappeared
        self.prev_centroids = {}  # id -> prev centroid

    def _centroid(self, box):
        x1,y1,x2,y2 = box
        return np.array([(x1+x2)/2.0, (y1+y2)/2.0], dtype=float)

    def update(self, rects):
        # compute current centroids
        centroids = [self._centroid(r) for r in rects]
        speeds = {}

        if len(self.objects) == 0:
            for c in centroids:
                self.objects[self.next_id] = c
                self.prev_centroids[self.next_id] = c
                self.disappeared[self.next_id] = 0
                self.next_id += 1
        else:
            # match by nearest neighbor
            obj_ids = list(self.objects.keys())
            obj_centroids = np.array([self.objects[i] for i in obj_ids]) if obj_ids else np.empty((0,2))
            for c in centroids:
                if obj_centroids.size == 0:
                    oid = self.next_id
                    self.next_id += 1
                else:
                    dists = np.linalg.norm(obj_centroids - c, axis=1)
                    idx = int(np.argmin(dists))
                    oid = obj_ids[idx]
                    obj_centroids[idx] = np.array([1e9,1e9])  # mark used
                self.objects[oid] = c
                self.disappeared[oid] = 0

            # mark disappeared
            current_ids = set([i for i in self.objects.keys()])
            for oid in list(self.disappeared.keys()):
                if oid not in current_ids:
                    self.disappeared[oid] += 1
                    if self.disappeared[oid] > self.max_disappeared:
                        self.objects.pop(oid, None)
                        self.prev_centroids.pop(oid, None)
                        self.disappeared.pop(oid, None)

        # compute speeds
        for oid, c in self.objects.items():
            prev = self.prev_centroids.get(oid, c)
            spd = float(np.linalg.norm(c - prev))
            speeds[oid] = spd
            self.prev_centroids[oid] = c

        return self.objects, speeds
