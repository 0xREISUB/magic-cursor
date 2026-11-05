"""Fare sallama algılama: yalnızca bilinçli, yerinde, yatay ve hızlı bir sallamayı kabul eder."""
from collections import deque

# Varsayılanlar; config.json içindeki "wiggle" anahtarıyla değiştirilebilir.
DEFAULTS = {
    'stroke_px': 70,      # bir vuruşun (tek yöne hareket) en az uzunluğu
    'flips': 6,           # gereken yön değişimi sayısı
    'window_s': 1.0,      # bu yön değişimlerinin sığması gereken süre
    'max_span_px': 450,   # sallama boyunca toplam yatay yayılım (yerinde sallama)
    'max_dy_ratio': 0.5,  # dikey hareket / yatay hareket oranı üst sınırı
    'cooldown_s': 1.5,    # tetiklendikten sonra bekleme süresi
}


class WiggleDetector:
    def __init__(self, overrides=None):
        self.p = dict(DEFAULTS, **(overrides or {}))
        self.samples = deque()   # (t, x, y)
        self.flips = deque()     # yön değişim zamanları
        self.last = None
        self.dir = 0
        self.acc = 0.0
        self.cooldown_until = 0.0

    def reset(self, now=0.0, cooldown=False):
        self.samples.clear()
        self.flips.clear()
        self.last, self.dir, self.acc = None, 0, 0.0
        if cooldown:
            self.cooldown_until = now + self.p['cooldown_s']

    def feed(self, x, y, t):
        """Yeni imleç konumu; geçerli bir sallama tamamlandıysa True döner."""
        p = self.p
        if t < self.cooldown_until:
            self.last = (x, y)
            return False
        if self.last is None:
            self.last = (x, y)
            return False
        dx, dy = x - self.last[0], y - self.last[1]
        self.last = (x, y)
        if dx == 0 and dy == 0:
            return False
        self.samples.append((t, x, y, abs(dx), abs(dy)))
        while self.samples and t - self.samples[0][0] > p['window_s']:
            self.samples.popleft()

        d = (dx > 0) - (dx < 0)
        if d == self.dir:
            self.acc += abs(dx)
        elif d and abs(dx) >= 4:  # dönüş noktasındaki 1-3 px titremeyi yok say
            if self.acc >= p['stroke_px']:
                self.flips.append(t)
            self.dir, self.acc = d, abs(dx)
        while self.flips and t - self.flips[0] > p['window_s']:
            self.flips.popleft()
        if len(self.flips) < p['flips']:
            return False

        # yerinde ve yatay mı?
        xs = [s[1] for s in self.samples]
        sum_dx = sum(s[3] for s in self.samples)
        sum_dy = sum(s[4] for s in self.samples)
        if max(xs) - min(xs) > p['max_span_px'] or sum_dy > p['max_dy_ratio'] * sum_dx:
            self.flips.clear()
            return False
        self.reset(t, cooldown=True)
        return True
