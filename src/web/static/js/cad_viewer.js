/**
 * Interactive 2D CAD Canvas Viewer & Geometry Editor.
 * High-performance vector rendering in true millimeter CAD coordinates.
 * Features:
 *   - Pan & Smooth Zoom
 *   - Select & Multi-Select Lines with Hit Testing
 *   - Delete Selected Lines with Undo / Redo
 *   - Draw Lines with Smart Endpoint Snapping & 45° Ortho Lock
 *   - Custom Angle Measurement Tool (between 2 lines or 3 points)
 *   - Custom Distance / Caliper Measurement Tool (between 2 points)
 *   - Dimension Annotations & Angle Arcs
 *   - Heatmap, Anchors, Symmetry Axis layers
 */

class CADViewer {
  constructor(canvasId) {
    this.canvas = document.getElementById(canvasId);
    this.ctx = this.canvas.getContext('2d');

    // Camera / View state
    this.viewCenterX = 0.0; // World mm
    this.viewCenterY = 0.0;
    this.scale = 1.0;       // Pixels per mm

    // Geometry data
    this.originalModel = null;
    this.repairedModel = null;
    this.axis = null;
    this.heatmapPoints = [];
    this.anchors = [];

    // Layer visibility
    this.layers = {
      original: true,
      axis: true,
      reflected: true,
      heatmap: true,
      anchors: true,
      repaired: false,
      measurements: true
    };

    // Tool Modes: 'select' | 'pan' | 'draw_line' | 'measure_angle' | 'measure_distance'
    this.toolMode = 'select';

    // Selection & Editing State
    this.selectedLineIndices = new Set();
    this.hoveredLineIndex = -1;
    this.undoStack = [];
    this.redoStack = [];

    // Drawing Line State
    this.drawStartPoint = null;     // { x, y } in world mm
    this.mouseWorld = { x: 0, y: 0 };
    this.snappedPoint = null;       // { x, y, type: 'endpoint' }

    // Measurement State
    this.measurements = [];         // Array of persistent measurements: { id, type, ... }
    this.measurePoints = [];        // Transient points clicked for active measurement
    this.measureLines = [];         // Transient lines clicked for active angle tool
    this.nextMeasureId = 1;

    // Interaction State
    this.isDragging = false;
    this.dragStartX = 0;
    this.dragStartY = 0;
    this.dragStartCenterX = 0;
    this.dragStartCenterY = 0;
    this.isShiftDown = false;

    // Callbacks
    this.onCoordsUpdate = null;
    this.onSelectionChange = null;
    this.onGeometryChange = null;
    this.onMeasurementsChange = null;
    this.onPromptUpdate = null;

    this.initEvents();
    this.resize();
    window.addEventListener('resize', () => this.resize());
  }

  resize() {
    const rect = this.canvas.parentElement.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    this.canvas.width = rect.width * dpr;
    this.canvas.height = rect.height * dpr;
    this.ctx.resetTransform();
    this.ctx.scale(dpr, dpr);
    this.cssWidth = rect.width;
    this.cssHeight = rect.height;
    this.render();
  }

  worldToScreen(wx, wy) {
    const sx = (wx - this.viewCenterX) * this.scale + this.cssWidth / 2;
    const sy = -(wy - this.viewCenterY) * this.scale + this.cssHeight / 2;
    return { x: sx, y: sy };
  }

  screenToWorld(sx, sy) {
    const wx = (sx - this.cssWidth / 2) / this.scale + this.viewCenterX;
    const wy = -(sy - this.cssHeight / 2) / this.scale + this.viewCenterY;
    return { x: wx, y: wy };
  }

  fitToModel(bbox) {
    if (!bbox || bbox.width <= 0 || bbox.height <= 0) return;

    this.viewCenterX = (bbox.min_x + bbox.max_x) / 2;
    this.viewCenterY = (bbox.min_y + bbox.max_y) / 2;

    const pad = 60; // pixels padding
    const availW = Math.max(100, this.cssWidth - pad * 2);
    const availH = Math.max(100, this.cssHeight - pad * 2);

    const scaleX = availW / bbox.width;
    const scaleY = availH / bbox.height;
    this.scale = Math.min(scaleX, scaleY);

    this.render();
  }

  setModelData(origModel, axisData, heatmap, anchors) {
    this.originalModel = origModel ? JSON.parse(JSON.stringify(origModel)) : null;
    this.axis = axisData;
    this.heatmapPoints = heatmap || [];
    this.anchors = anchors || [];
    this.repairedModel = null;
    this.layers.repaired = false;
    this.selectedLineIndices.clear();
    this.undoStack = [];
    this.redoStack = [];
    this.measurePoints = [];
    this.measureLines = [];

    if (origModel && origModel.bbox) {
      this.fitToModel(origModel.bbox);
    }
  }

  setRepairedModel(repairedModel) {
    this.repairedModel = repairedModel;
    this.layers.repaired = true;
    this.layers.heatmap = false;
    this.render();
  }

  toggleLayer(layerName) {
    if (this.layers.hasOwnProperty(layerName)) {
      this.layers[layerName] = !this.layers[layerName];
      this.render();
      return this.layers[layerName];
    }
    return false;
  }

  setToolMode(mode) {
    this.toolMode = mode;
    this.drawStartPoint = null;
    this.measurePoints = [];
    this.measureLines = [];
    this.snappedPoint = null;
    this.updateCursor();
    this.notifyPrompt();
    this.render();
  }

  updateCursor() {
    if (this.toolMode === 'pan') {
      this.canvas.style.cursor = 'grab';
    } else if (this.toolMode === 'draw_line') {
      this.canvas.style.cursor = 'crosshair';
    } else if (this.toolMode === 'measure_angle' || this.toolMode === 'measure_distance') {
      this.canvas.style.cursor = 'crosshair';
    } else {
      this.canvas.style.cursor = 'default';
    }
  }

  notifyPrompt() {
    if (!this.onPromptUpdate) return;
    let msg = '';
    if (this.toolMode === 'select') {
      msg = 'Nhấp chuột vào nét để chọn. Bấm Delete để xóa. Giữ Shift để chọn nhiều nét.';
    } else if (this.toolMode === 'draw_line') {
      msg = this.drawStartPoint 
        ? 'Nhấp điểm thứ hai để kết thúc nét. Giữ Shift để khóa góc 0°/45°/90°/135°. Esc để hủy.'
        : 'Nhấp điểm đầu tiên để vẽ nét mới. Tự động bắt dính (snap) đầu mút lân cận.';
    } else if (this.toolMode === 'measure_angle') {
      if (this.measureLines.length === 1) {
        msg = 'Đã chọn đường thứ nhất. Nhấp tiếp vào đường thẳng thứ hai để đo góc kẹp.';
      } else {
        msg = 'Nhấp chọn 2 đường thẳng bất kỳ trên bản vẽ để đo góc chính xác.';
      }
    } else if (this.toolMode === 'measure_distance') {
      msg = this.measurePoints.length === 1
        ? 'Nhấp điểm thứ hai để hoàn tất đo khoảng cách (mm). Esc để hủy.'
        : 'Nhấp điểm thứ nhất để đo khoảng cách (tự động snap đầu mút).';
    } else if (this.toolMode === 'pan') {
      msg = 'Giữ chuột trái hoặc chuột giữa để kéo di chuyển bản vẽ CAD.';
    }
    this.onPromptUpdate(msg);
  }

  // --- Geometry Editing: Add / Delete / Undo / Redo ---

  saveUndoSnapshot() {
    if (!this.originalModel) return;
    const snapshot = JSON.parse(JSON.stringify(this.originalModel.lines));
    this.undoStack.push(snapshot);
    this.redoStack = []; // Clear redo stack on new modification
  }

  deleteSelected() {
    if (!this.originalModel || this.selectedLineIndices.size === 0) return false;
    this.saveUndoSnapshot();

    const remainingLines = [];
    for (let i = 0; i < this.originalModel.lines.length; i++) {
      if (!this.selectedLineIndices.has(i)) {
        remainingLines.push(this.originalModel.lines[i]);
      }
    }

    this.originalModel.lines = remainingLines;
    this.selectedLineIndices.clear();
    this.hoveredLineIndex = -1;
    this.render();

    if (this.onGeometryChange) this.onGeometryChange(this.originalModel.lines);
    if (this.onSelectionChange) this.onSelectionChange([]);
    return true;
  }

  addLine(p1, p2) {
    if (!this.originalModel) return;
    const dist = Math.hypot(p2.x - p1.x, p2.y - p1.y);
    if (dist < 1e-3) return;

    this.saveUndoSnapshot();
    const newLine = {
      x1: Math.round(p1.x * 1000) / 1000,
      y1: Math.round(p1.y * 1000) / 1000,
      x2: Math.round(p2.x * 1000) / 1000,
      y2: Math.round(p2.y * 1000) / 1000,
      layer: '0'
    };

    this.originalModel.lines.push(newLine);
    this.render();

    if (this.onGeometryChange) this.onGeometryChange(this.originalModel.lines);
  }

  undo() {
    if (!this.originalModel || this.undoStack.length === 0) return false;
    const currentLines = JSON.parse(JSON.stringify(this.originalModel.lines));
    this.redoStack.push(currentLines);

    const prevLines = this.undoStack.pop();
    this.originalModel.lines = prevLines;
    this.selectedLineIndices.clear();
    this.hoveredLineIndex = -1;
    this.render();

    if (this.onGeometryChange) this.onGeometryChange(this.originalModel.lines);
    if (this.onSelectionChange) this.onSelectionChange([]);
    return true;
  }

  redo() {
    if (!this.originalModel || this.redoStack.length === 0) return false;
    const currentLines = JSON.parse(JSON.stringify(this.originalModel.lines));
    this.undoStack.push(currentLines);

    const nextLines = this.redoStack.pop();
    this.originalModel.lines = nextLines;
    this.selectedLineIndices.clear();
    this.hoveredLineIndex = -1;
    this.render();

    if (this.onGeometryChange) this.onGeometryChange(this.originalModel.lines);
    if (this.onSelectionChange) this.onSelectionChange([]);
    return true;
  }

  clearMeasurements() {
    this.measurements = [];
    this.measurePoints = [];
    this.measureLines = [];
    this.render();
    if (this.onMeasurementsChange) this.onMeasurementsChange(this.measurements);
  }

  // --- Geometric Calculations & Snapping ---

  pointToSegmentDistSq(px, py, x1, y1, x2, y2) {
    const dx = x2 - x1;
    const dy = y2 - y1;
    const lenSq = dx * dx + dy * dy;
    if (lenSq === 0) return (px - x1) * (px - x1) + (py - y1) * (py - y1);

    let t = ((px - x1) * dx + (py - y1) * dy) / lenSq;
    t = Math.max(0, Math.min(1, t));
    const projX = x1 + t * dx;
    const projY = y1 + t * dy;
    return (px - projX) * (px - projX) + (py - projY) * (py - projY);
  }

  findNearestLine(screenX, screenY, maxPixelDist = 9) {
    if (!this.originalModel || !this.originalModel.lines) return -1;
    let bestIdx = -1;
    let minDistSq = maxPixelDist * maxPixelDist;

    for (let i = 0; i < this.originalModel.lines.length; i++) {
      const l = this.originalModel.lines[i];
      const p1 = this.worldToScreen(l.x1, l.y1);
      const p2 = this.worldToScreen(l.x2, l.y2);
      const dSq = this.pointToSegmentDistSq(screenX, screenY, p1.x, p1.y, p2.x, p2.y);
      if (dSq < minDistSq) {
        minDistSq = dSq;
        bestIdx = i;
      }
    }
    return bestIdx;
  }

  findNearestEndpoint(screenX, screenY, maxPixelDist = 12) {
    if (!this.originalModel || !this.originalModel.lines) return null;
    let bestPt = null;
    let minDistSq = maxPixelDist * maxPixelDist;

    for (const l of this.originalModel.lines) {
      const sp1 = this.worldToScreen(l.x1, l.y1);
      const dSq1 = (screenX - sp1.x) * (screenX - sp1.x) + (screenY - sp1.y) * (screenY - sp1.y);
      if (dSq1 < minDistSq) {
        minDistSq = dSq1;
        bestPt = { x: l.x1, y: l.y1, type: 'endpoint' };
      }

      const sp2 = this.worldToScreen(l.x2, l.y2);
      const dSq2 = (screenX - sp2.x) * (screenX - sp2.x) + (screenY - sp2.y) * (screenY - sp2.y);
      if (dSq2 < minDistSq) {
        minDistSq = dSq2;
        bestPt = { x: l.x2, y: l.y2, type: 'endpoint' };
      }
    }
    return bestPt;
  }

  applyOrthoConstraint(startPt, endPt) {
    const dx = endPt.x - startPt.x;
    const dy = endPt.y - startPt.y;
    const dist = Math.hypot(dx, dy);
    if (dist < 1e-4) return endPt;

    let ang = Math.atan2(dy, dx); // radians
    const step = Math.PI / 4;      // 45 degrees
    ang = Math.round(ang / step) * step;

    return {
      x: startPt.x + dist * Math.cos(ang),
      y: startPt.y + dist * Math.sin(ang)
    };
  }

  computeLineIntersection(l1, l2) {
    const x1 = l1.x1, y1 = l1.y1, x2 = l1.x2, y2 = l1.y2;
    const x3 = l2.x1, y3 = l2.y1, x4 = l2.x2, y4 = l2.y2;

    const denom = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4);
    if (Math.abs(denom) < 1e-6) {
      // Parallel lines: use midpoint of closest endpoints
      return { x: (x1 + x3) * 0.5, y: (y1 + y3) * 0.5 };
    }

    const t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / denom;
    return {
      x: x1 + t * (x2 - x1),
      y: y1 + t * (y2 - y1)
    };
  }

  computeAngleBetweenLines(l1, l2) {
    const v1x = l1.x2 - l1.x1;
    const v1y = l1.y2 - l1.y1;
    const v2x = l2.x2 - l2.x1;
    const v2y = l2.y2 - l2.y1;

    const len1 = Math.hypot(v1x, v1y);
    const len2 = Math.hypot(v2x, v2y);
    if (len1 < 1e-6 || len2 < 1e-6) return 0.0;

    let dot = (v1x * v2x + v1y * v2y) / (len1 * len2);
    dot = Math.max(-1.0, Math.min(1.0, dot));
    let deg = Math.acos(dot) * (180.0 / Math.PI);
    return deg;
  }

  // --- Event Handling ---

  initEvents() {
    // Keyboard events
    window.addEventListener('keydown', (e) => {
      if (e.key === 'Shift') {
        this.isShiftDown = true;
        this.render();
      }
      if (e.key === 'Escape') {
        this.drawStartPoint = null;
        this.measurePoints = [];
        this.measureLines = [];
        this.snappedPoint = null;
        this.notifyPrompt();
        this.render();
      }
      if (e.key === 'Delete' || e.key === 'Backspace') {
        // Prevent backspace navigating away
        if (e.target.tagName !== 'INPUT' && e.target.tagName !== 'TEXTAREA') {
          if (this.selectedLineIndices.size > 0) {
            e.preventDefault();
            this.deleteSelected();
          }
        }
      }
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'z') {
        e.preventDefault();
        if (e.shiftKey) {
          this.redo();
        } else {
          this.undo();
        }
      }
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'y') {
        e.preventDefault();
        this.redo();
      }
    });

    window.addEventListener('keyup', (e) => {
      if (e.key === 'Shift') {
        this.isShiftDown = false;
        this.render();
      }
    });

    // Wheel zoom
    this.canvas.addEventListener('wheel', (e) => {
      e.preventDefault();
      const mouse = this.getCanvasMousePos(e);
      const worldBefore = this.screenToWorld(mouse.x, mouse.y);

      const factor = e.deltaY < 0 ? 1.15 : 0.87;
      this.scale = Math.max(0.05, Math.min(100.0, this.scale * factor));

      const worldAfter = this.screenToWorld(mouse.x, mouse.y);
      this.viewCenterX += (worldBefore.x - worldAfter.x);
      this.viewCenterY += (worldBefore.y - worldAfter.y);

      this.render();
    }, { passive: false });

    // Mouse Down
    this.canvas.addEventListener('mousedown', (e) => {
      const pos = this.getCanvasMousePos(e);
      const world = this.screenToWorld(pos.x, pos.y);

      // Middle click always pans
      if (e.button === 1 || this.toolMode === 'pan') {
        this.isDragging = true;
        this.dragStartX = pos.x;
        this.dragStartY = pos.y;
        this.dragStartCenterX = this.viewCenterX;
        this.dragStartCenterY = this.viewCenterY;
        this.canvas.style.cursor = 'grabbing';
        return;
      }

      if (e.button === 0) { // Left Click
        this.handleLeftClick(pos, world, e.shiftKey);
      }
    });

    // Mouse Move
    window.addEventListener('mousemove', (e) => {
      const pos = this.getCanvasMousePos(e);
      const world = this.screenToWorld(pos.x, pos.y);
      this.mouseWorld = world;

      if (this.onCoordsUpdate) {
        this.onCoordsUpdate(world.x, world.y);
      }

      if (this.isDragging) {
        const dx = (pos.x - this.dragStartX) / this.scale;
        const dy = (pos.y - this.dragStartY) / this.scale;
        this.viewCenterX = this.dragStartCenterX - dx;
        this.viewCenterY = this.dragStartCenterY + dy;
        this.render();
        return;
      }

      // Check Snapping when drawing or measuring distance
      if (this.toolMode === 'draw_line' || this.toolMode === 'measure_distance') {
        const snap = this.findNearestEndpoint(pos.x, pos.y, 14);
        if (snap) {
          this.snappedPoint = snap;
        } else {
          this.snappedPoint = null;
        }
        this.render();
      } else if (this.toolMode === 'select' || this.toolMode === 'measure_angle') {
        const hIdx = this.findNearestLine(pos.x, pos.y, 9);
        if (hIdx !== this.hoveredLineIndex) {
          this.hoveredLineIndex = hIdx;
          this.render();
        }
      }
    });

    // Mouse Up
    window.addEventListener('mouseup', () => {
      if (this.isDragging) {
        this.isDragging = false;
        this.updateCursor();
      }
    });
  }

  handleLeftClick(pos, world, isShift) {
    if (this.toolMode === 'select') {
      const clickedIdx = this.findNearestLine(pos.x, pos.y, 9);
      if (clickedIdx >= 0) {
        if (isShift) {
          if (this.selectedLineIndices.has(clickedIdx)) {
            this.selectedLineIndices.delete(clickedIdx);
          } else {
            this.selectedLineIndices.add(clickedIdx);
          }
        } else {
          this.selectedLineIndices.clear();
          this.selectedLineIndices.add(clickedIdx);
        }
      } else if (!isShift) {
        this.selectedLineIndices.clear();
      }

      const selectedLines = [];
      if (this.originalModel) {
        this.selectedLineIndices.forEach(idx => {
          if (this.originalModel.lines[idx]) selectedLines.push(this.originalModel.lines[idx]);
        });
      }

      if (this.onSelectionChange) this.onSelectionChange(selectedLines);
      this.render();

    } else if (this.toolMode === 'draw_line') {
      const pt = this.snappedPoint || world;
      if (!this.drawStartPoint) {
        this.drawStartPoint = { x: pt.x, y: pt.y };
        this.notifyPrompt();
        this.render();
      } else {
        let finalPt = pt;
        if (this.isShiftDown) {
          finalPt = this.applyOrthoConstraint(this.drawStartPoint, pt);
        }
        this.addLine(this.drawStartPoint, finalPt);
        this.drawStartPoint = null;
        this.notifyPrompt();
        this.render();
      }

    } else if (this.toolMode === 'measure_distance') {
      const pt = this.snappedPoint || world;
      this.measurePoints.push({ x: pt.x, y: pt.y });
      if (this.measurePoints.length === 2) {
        const p1 = this.measurePoints[0];
        const p2 = this.measurePoints[1];
        const dist = Math.hypot(p2.x - p1.x, p2.y - p1.y);

        this.measurements.push({
          id: this.nextMeasureId++,
          type: 'distance',
          p1: p1,
          p2: p2,
          distMm: dist
        });

        this.measurePoints = [];
        this.notifyPrompt();
        if (this.onMeasurementsChange) this.onMeasurementsChange(this.measurements);
      } else {
        this.notifyPrompt();
      }
      this.render();

    } else if (this.toolMode === 'measure_angle') {
      const clickedIdx = this.findNearestLine(pos.x, pos.y, 10);
      if (clickedIdx >= 0 && this.originalModel && this.originalModel.lines[clickedIdx]) {
        const line = this.originalModel.lines[clickedIdx];
        this.measureLines.push(line);

        if (this.measureLines.length === 2) {
          const l1 = this.measureLines[0];
          const l2 = this.measureLines[1];
          const angleDeg = this.computeAngleBetweenLines(l1, l2);
          const apex = this.computeLineIntersection(l1, l2);

          this.measurements.push({
            id: this.nextMeasureId++,
            type: 'angle',
            l1: l1,
            l2: l2,
            apex: apex,
            angleDeg: angleDeg
          });

          this.measureLines = [];
          this.notifyPrompt();
          if (this.onMeasurementsChange) this.onMeasurementsChange(this.measurements);
        } else {
          this.notifyPrompt();
        }
        this.render();
      }
    }
  }

  getCanvasMousePos(e) {
    const rect = this.canvas.getBoundingClientRect();
    return {
      x: e.clientX - rect.left,
      y: e.clientY - rect.top
    };
  }

  // --- Rendering Pipeline ---

  render() {
    const ctx = this.ctx;
    ctx.clearRect(0, 0, this.cssWidth, this.cssHeight);

    if (!this.originalModel && !this.repairedModel) return;

    // 1. Draw Repaired Geometry if active
    if (this.layers.repaired && this.repairedModel) {
      ctx.strokeStyle = '#10b981'; // Emerald Green
      ctx.lineWidth = 1.8;
      ctx.setLineDash([]);
      this.drawModelEntities(this.repairedModel, ctx);
    }

    // 2. Draw Original Geometry
    if (this.layers.original && this.originalModel) {
      ctx.strokeStyle = this.layers.repaired ? 'rgba(255, 255, 255, 0.25)' : '#e5e7eb';
      ctx.lineWidth = this.layers.repaired ? 1.0 : 1.4;
      ctx.setLineDash([]);
      this.drawModelEntities(this.originalModel, ctx);
    }

    // 3. Draw Hovered & Selected Lines
    if (this.originalModel) {
      // Hovered Line
      if (this.hoveredLineIndex >= 0 && this.originalModel.lines[this.hoveredLineIndex]) {
        const hl = this.originalModel.lines[this.hoveredLineIndex];
        ctx.strokeStyle = '#38bdf8'; // Sky Blue
        ctx.lineWidth = 2.4;
        ctx.setLineDash([]);
        const p1 = this.worldToScreen(hl.x1, hl.y1);
        const p2 = this.worldToScreen(hl.x2, hl.y2);
        ctx.beginPath();
        ctx.moveTo(p1.x, p1.y);
        ctx.lineTo(p2.x, p2.y);
        ctx.stroke();
      }

      // Selected Lines
      if (this.selectedLineIndices.size > 0) {
        ctx.strokeStyle = '#fbbf24'; // Amber Gold
        ctx.fillStyle = '#fbbf24';
        ctx.lineWidth = 2.6;
        ctx.setLineDash([]);

        this.selectedLineIndices.forEach(idx => {
          const sl = this.originalModel.lines[idx];
          if (!sl) return;
          const p1 = this.worldToScreen(sl.x1, sl.y1);
          const p2 = this.worldToScreen(sl.x2, sl.y2);
          ctx.beginPath();
          ctx.moveTo(p1.x, p1.y);
          ctx.lineTo(p2.x, p2.y);
          ctx.stroke();

          // Endpoint handle circles
          ctx.beginPath();
          ctx.arc(p1.x, p1.y, 4.5, 0, Math.PI * 2);
          ctx.arc(p2.x, p2.y, 4.5, 0, Math.PI * 2);
          ctx.fill();
        });
      }
    }

    // 4. Draw Reflected Geometry
    if (this.layers.reflected && this.originalModel && this.axis && !this.layers.repaired) {
      ctx.strokeStyle = '#00f2fe'; // Neon Cyan
      ctx.lineWidth = 1.0;
      ctx.setLineDash([4, 4]);
      this.drawReflectedEntities(this.originalModel, this.axis, ctx);
      ctx.setLineDash([]);
    }

    // 5. Draw Heatmap Points
    if (this.layers.heatmap && this.heatmapPoints && this.heatmapPoints.length > 0 && !this.layers.repaired) {
      this.drawHeatmap(ctx);
    }

    // 6. Draw Symmetry Axis Line
    if (this.layers.axis && this.axis) {
      this.drawAxis(ctx);
    }

    // 7. Draw Design Anchors
    if (this.layers.anchors && this.anchors && this.anchors.length > 0 && !this.layers.repaired) {
      this.drawAnchors(ctx);
    }

    // 8. Draw Active Line Drawing Preview
    if (this.toolMode === 'draw_line' && this.drawStartPoint) {
      const p1 = this.worldToScreen(this.drawStartPoint.x, this.drawStartPoint.y);
      let targetPt = this.snappedPoint || this.mouseWorld;
      if (this.isShiftDown) {
        targetPt = this.applyOrthoConstraint(this.drawStartPoint, targetPt);
      }
      const p2 = this.worldToScreen(targetPt.x, targetPt.y);

      ctx.strokeStyle = '#00f2fe';
      ctx.lineWidth = 2.0;
      ctx.setLineDash([6, 3]);
      ctx.beginPath();
      ctx.moveTo(p1.x, p1.y);
      ctx.lineTo(p2.x, p2.y);
      ctx.stroke();
      ctx.setLineDash([]);

      // Start handle
      ctx.fillStyle = '#00f2fe';
      ctx.beginPath();
      ctx.arc(p1.x, p1.y, 5, 0, Math.PI * 2);
      ctx.fill();

      // Tooltip with length and angle
      const dist = Math.hypot(targetPt.x - this.drawStartPoint.x, targetPt.y - this.drawStartPoint.y);
      const ang = Math.atan2(targetPt.y - this.drawStartPoint.y, targetPt.x - this.drawStartPoint.x) * 180 / Math.PI;
      const midX = (p1.x + p2.x) * 0.5;
      const midY = (p1.y + p2.y) * 0.5;
      this.drawBadge(ctx, midX, midY - 14, `L: ${dist.toFixed(2)} mm  ∠${ang.toFixed(1)}°`, '#00f2fe', '#000');
    }

    // 9. Draw Active Distance Measurement Preview
    if (this.toolMode === 'measure_distance' && this.measurePoints.length === 1) {
      const p1 = this.worldToScreen(this.measurePoints[0].x, this.measurePoints[0].y);
      const targetPt = this.snappedPoint || this.mouseWorld;
      const p2 = this.worldToScreen(targetPt.x, targetPt.y);

      ctx.strokeStyle = '#f59e0b'; // Amber
      ctx.lineWidth = 1.8;
      ctx.setLineDash([4, 4]);
      ctx.beginPath();
      ctx.moveTo(p1.x, p1.y);
      ctx.lineTo(p2.x, p2.y);
      ctx.stroke();
      ctx.setLineDash([]);

      const dist = Math.hypot(targetPt.x - this.measurePoints[0].x, targetPt.y - this.measurePoints[0].y);
      const midX = (p1.x + p2.x) * 0.5;
      const midY = (p1.y + p2.y) * 0.5;
      this.drawBadge(ctx, midX, midY - 14, `${dist.toFixed(2)} mm`, '#f59e0b', '#000');
    }

    // 10. Draw Active Measure Angle Preview (first clicked line highlight)
    if (this.toolMode === 'measure_angle' && this.measureLines.length === 1) {
      const l1 = this.measureLines[0];
      const p1 = this.worldToScreen(l1.x1, l1.y1);
      const p2 = this.worldToScreen(l1.x2, l1.y2);
      ctx.strokeStyle = '#a855f7'; // Purple
      ctx.lineWidth = 3.0;
      ctx.beginPath();
      ctx.moveTo(p1.x, p1.y);
      ctx.lineTo(p2.x, p2.y);
      ctx.stroke();
      this.drawBadge(ctx, (p1.x + p2.x) * 0.5, (p1.y + p2.y) * 0.5 - 12, 'Đường 1 (Nhấp đường thứ 2)', '#a855f7', '#fff');
    }

    // 11. Draw Snapped Endpoint Indicator
    if (this.snappedPoint) {
      const sp = this.worldToScreen(this.snappedPoint.x, this.snappedPoint.y);
      ctx.strokeStyle = '#00f2fe';
      ctx.fillStyle = 'rgba(0, 242, 254, 0.3)';
      ctx.lineWidth = 2.0;
      ctx.beginPath();
      ctx.arc(sp.x, sp.y, 7, 0, Math.PI * 2);
      ctx.fill();
      ctx.stroke();
    }

    // 12. Draw Persistent Measurements
    if (this.layers.measurements && this.measurements.length > 0) {
      this.drawPersistentMeasurements(ctx);
    }
  }

  drawPersistentMeasurements(ctx) {
    for (const m of this.measurements) {
      if (m.type === 'distance') {
        const p1 = this.worldToScreen(m.p1.x, m.p1.y);
        const p2 = this.worldToScreen(m.p2.x, m.p2.y);

        ctx.strokeStyle = '#38bdf8'; // Sky blue dimension line
        ctx.lineWidth = 1.6;
        ctx.setLineDash([]);
        ctx.beginPath();
        ctx.moveTo(p1.x, p1.y);
        ctx.lineTo(p2.x, p2.y);
        ctx.stroke();

        // Tick marks at endpoints
        const dx = p2.x - p1.x;
        const dy = p2.y - p1.y;
        const len = Math.hypot(dx, dy);
        if (len > 1e-4) {
          const nx = -dy / len * 6;
          const ny = dx / len * 6;

          ctx.beginPath();
          ctx.moveTo(p1.x - nx, p1.y - ny);
          ctx.lineTo(p1.x + nx, p1.y + ny);
          ctx.moveTo(p2.x - nx, p2.y - ny);
          ctx.lineTo(p2.x + nx, p2.y + ny);
          ctx.stroke();
        }

        const midX = (p1.x + p2.x) * 0.5;
        const midY = (p1.y + p2.y) * 0.5;
        this.drawBadge(ctx, midX, midY - 12, `${m.distMm.toFixed(2)} mm`, 'rgba(15, 23, 42, 0.85)', '#38bdf8', '#38bdf8');

      } else if (m.type === 'angle') {
        const apexScr = this.worldToScreen(m.apex.x, m.apex.y);
        const l1Mid = this.worldToScreen((m.l1.x1 + m.l1.x2) * 0.5, (m.l1.y1 + m.l1.y2) * 0.5);
        const l2Mid = this.worldToScreen((m.l2.x1 + m.l2.x2) * 0.5, (m.l2.y1 + m.l2.y2) * 0.5);

        const a1 = Math.atan2(l1Mid.y - apexScr.y, l1Mid.x - apexScr.x);
        const a2 = Math.atan2(l2Mid.y - apexScr.y, l2Mid.x - apexScr.x);

        const arcR = 28;
        ctx.strokeStyle = '#c084fc'; // Purple arc
        ctx.lineWidth = 1.8;
        ctx.beginPath();
        ctx.arc(apexScr.x, apexScr.y, arcR, Math.min(a1, a2), Math.max(a1, a2));
        ctx.stroke();

        const midAng = (a1 + a2) * 0.5;
        const textX = apexScr.x + (arcR + 18) * Math.cos(midAng);
        const textY = apexScr.y + (arcR + 18) * Math.sin(midAng);
        this.drawBadge(ctx, textX, textY, `∠ ${m.angleDeg.toFixed(1)}°`, 'rgba(15, 23, 42, 0.85)', '#c084fc', '#c084fc');
      }
    }
  }

  drawBadge(ctx, x, y, text, bgColor, textColor, borderColor = null) {
    ctx.font = '11px JetBrains Mono, monospace';
    const textWidth = ctx.measureText(text).width;
    const padX = 7;
    const padY = 3.5;
    const w = textWidth + padX * 2;
    const h = 18;
    const bx = x - w / 2;
    const by = y - h / 2;

    ctx.fillStyle = bgColor;
    ctx.beginPath();
    ctx.roundRect(bx, by, w, h, 4);
    ctx.fill();

    if (borderColor) {
      ctx.strokeStyle = borderColor;
      ctx.lineWidth = 1.2;
      ctx.stroke();
    }

    ctx.fillStyle = textColor;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(text, x, y);
  }

  drawModelEntities(model, ctx) {
    ctx.beginPath();
    for (const line of model.lines) {
      const p1 = this.worldToScreen(line.x1, line.y1);
      const p2 = this.worldToScreen(line.x2, line.y2);
      ctx.moveTo(p1.x, p1.y);
      ctx.lineTo(p2.x, p2.y);
    }
    ctx.stroke();

    for (const arc of model.arcs) {
      const c = this.worldToScreen(arc.cx, arc.cy);
      const r = arc.radius * this.scale;
      const sAng = -arc.start_ang;
      const eAng = -arc.end_ang;
      ctx.beginPath();
      ctx.arc(c.x, c.y, r, sAng, eAng, arc.is_ccw);
      ctx.stroke();
    }
  }

  drawReflectedEntities(model, axis, ctx) {
    const axAngle = (axis.angle_deg * Math.PI) / 180;
    const axDirX = Math.cos(axAngle);
    const axDirY = Math.sin(axAngle);
    const ox = axis.origin.x;
    const oy = axis.origin.y;

    const reflectPoint = (x, y) => {
      const vx = x - ox;
      const vy = y - oy;
      const projLen = vx * axDirX + vy * axDirY;
      const projX = ox + axDirX * projLen;
      const projY = oy + axDirY * projLen;
      return {
        x: 2 * projX - x,
        y: 2 * projY - y
      };
    };

    ctx.beginPath();
    for (const line of model.lines) {
      const r1 = reflectPoint(line.x1, line.y1);
      const r2 = reflectPoint(line.x2, line.y2);
      const p1 = this.worldToScreen(r1.x, r1.y);
      const p2 = this.worldToScreen(r2.x, r2.y);
      ctx.moveTo(p1.x, p1.y);
      ctx.lineTo(p2.x, p2.y);
    }
    ctx.stroke();
  }

  drawAxis(ctx) {
    const axis = this.axis;
    const angleRad = (axis.angle_deg * Math.PI) / 180;
    const dirX = Math.cos(angleRad);
    const dirY = Math.sin(angleRad);

    const ox = axis.origin.x;
    const oy = axis.origin.y;

    const p1 = this.worldToScreen(ox - dirX * 2000, oy - dirY * 2000);
    const p2 = this.worldToScreen(ox + dirX * 2000, oy + dirY * 2000);

    ctx.beginPath();
    ctx.strokeStyle = '#ff5722'; // Laser Orange
    ctx.lineWidth = 2.0;
    ctx.setLineDash([8, 4]);
    ctx.moveTo(p1.x, p1.y);
    ctx.lineTo(p2.x, p2.y);
    ctx.stroke();
    ctx.setLineDash([]);

    const centerScreen = this.worldToScreen(ox, oy);
    ctx.fillStyle = '#ff5722';
    ctx.font = '11px JetBrains Mono, monospace';
    ctx.textAlign = 'left';
    ctx.textBaseline = 'bottom';
    ctx.fillText(`TRỤC ${axis.angle_deg.toFixed(1)}° (X=${ox.toFixed(2)})`, centerScreen.x + 8, centerScreen.y - 8);
  }

  drawAnchors(ctx) {
    for (const a of this.anchors) {
      const scr = this.worldToScreen(a.x, a.y);
      if (a.anchor_type === 'panel_center') {
        ctx.fillStyle = '#ff5722';
        ctx.beginPath();
        ctx.arc(scr.x, scr.y, 6, 0, Math.PI * 2);
        ctx.fill();
        ctx.strokeStyle = '#ffffff';
        ctx.lineWidth = 2;
        ctx.stroke();
      } else if (a.anchor_type === 'outer_corner') {
        ctx.fillStyle = '#00f2fe';
        ctx.fillRect(scr.x - 4, scr.y - 4, 8, 8);
        ctx.strokeStyle = '#000000';
        ctx.lineWidth = 1.2;
        ctx.strokeRect(scr.x - 4, scr.y - 4, 8, 8);
      } else {
        ctx.fillStyle = '#a855f7';
        ctx.beginPath();
        ctx.arc(scr.x, scr.y, 4, 0, Math.PI * 2);
        ctx.fill();
      }
    }
  }

  drawHeatmap(ctx) {
    for (const p of this.heatmapPoints) {
      const sp = this.worldToScreen(p.x, p.y);
      const dev = p.dev;

      let color;
      if (dev < 0.5) {
        color = 'rgba(76, 29, 149, 0.7)';
      } else if (dev < 1.5) {
        color = 'rgba(192, 38, 211, 0.8)';
      } else if (dev < 3.0) {
        color = 'rgba(239, 68, 68, 0.9)';
      } else if (dev < 6.0) {
        color = 'rgba(249, 115, 22, 0.95)';
      } else {
        color = 'rgba(234, 179, 8, 1.0)';
      }

      ctx.fillStyle = color;
      ctx.beginPath();
      ctx.arc(sp.x, sp.y, 3.5, 0, Math.PI * 2);
      ctx.fill();
    }
  }
}
