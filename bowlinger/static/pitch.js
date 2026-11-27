/* Click-to-place pitch polygon. A rectangle from the API is just four points. */
function createPitchEditor() {
  return {
    points: [],
    closed: false,
    selected: -1,
    dragging: false,
    hit(point, limit = 14) {
      let found = -1;
      let best = limit * limit;
      this.points.forEach((item, index) => {
        const distance = (item.x - point.x) ** 2 + (item.y - point.y) ** 2;
        if (distance <= best) {
          best = distance;
          found = index;
        }
      });
      return found;
    },
    pointerDown(point) {
      const index = this.hit(point);
      if (index >= 0) {
        this.selected = index;
        this.dragging = true;
        return;
      }
      if (this.closed) return;
      this.points.push({ x: point.x, y: point.y });
      this.selected = this.points.length - 1;
    },
    pointerMove(point) {
      if (!this.dragging || this.selected < 0) return;
      this.points[this.selected] = { x: point.x, y: point.y };
    },
    pointerUp() {
      this.dragging = false;
    },
    removeAt(index) {
      if (index < 0 || index >= this.points.length) return;
      this.points.splice(index, 1);
      this.selected = this.points.length ? Math.min(index, this.points.length - 1) : -1;
      if (this.points.length < 3) this.closed = false;
    },
    removeSelected() {
      this.removeAt(this.selected >= 0 ? this.selected : this.points.length - 1);
    },
    complete() {
      this.closed = this.points.length >= 3;
      return this.closed;
    },
    clear() {
      this.points = [];
      this.closed = false;
      this.selected = -1;
      this.dragging = false;
    },
    load(polygon) {
      this.points = (polygon || []).map((point) => ({ x: point[0], y: point[1] }));
      this.closed = this.points.length >= 3;
      this.selected = -1;
    },
    coordinates() {
      return this.points.map((point) => [point.x, point.y]);
    },
    paint(context) {
      if (!this.points.length) return;
      context.beginPath();
      context.moveTo(this.points[0].x, this.points[0].y);
      for (let index = 1; index < this.points.length; index += 1) {
        context.lineTo(this.points[index].x, this.points[index].y);
      }
      if (this.closed) context.closePath();
      context.lineWidth = 3;
      context.strokeStyle = "#8fbf7f";
      if (this.closed) {
        context.fillStyle = "rgba(143, 191, 127, 0.35)";
        context.fill();
      }
      context.stroke();
      this.points.forEach((point, index) => {
        context.beginPath();
        context.fillStyle = index === this.selected ? "#f3efe2" : "#8fbf7f";
        context.arc(point.x, point.y, index === this.selected ? 7 : 5, 0, Math.PI * 2);
        context.fill();
      });
    },
  };
}
