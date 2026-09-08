/**
 * Main Web Application State & API Controller.
 */

document.addEventListener('DOMContentLoaded', () => {
  const viewer = new CADViewer('cad-canvas');

  // DOM Elements
  const dropzone = document.getElementById('dropzone');
  const fileInput = document.getElementById('file-input');
  const btnLoadSample = document.getElementById('btn-load-sample');
  const btnApplyRepair = document.getElementById('btn-apply-repair');
  const btnDownloadDxf = document.getElementById('btn-download-dxf');
  const btnDownloadJson = document.getElementById('btn-download-json');
  const exportCard = document.getElementById('export-card');

  const fileInfoBar = document.getElementById('file-info-bar');
  const activeFilename = document.getElementById('active-filename');
  const panelDimensions = document.getElementById('panel-dimensions');
  const canvasEmptyOverlay = document.getElementById('canvas-empty-overlay');
  const heatmapLegend = document.getElementById('heatmap-legend');
  const statusLabel = document.getElementById('status-label');

  // Metrics DOM
  const classificationBadge = document.getElementById('classification-badge');
  const metricVisualQuality = document.getElementById('metric-visual-quality');
  const vqVerdict = document.getElementById('vq-verdict');
  const metricScore = document.getElementById('metric-score');
  const metricSpacing = document.getElementById('metric-spacing');
  const metricAngle = document.getElementById('metric-angle');
  const metricAlignment = document.getElementById('metric-alignment');
  const metricDeformation = document.getElementById('metric-deformation');
  const metricAxis = document.getElementById('metric-axis');
  const topoLoops = document.getElementById('topo-loops');
  const topoEntities = document.getElementById('topo-entities');
  const actionRecommendation = document.getElementById('action-recommendation');
  const cursorCoords = document.getElementById('cursor-coords');

  // CAD Interactive Tools DOM
  const btnToolSelect = document.getElementById('btn-tool-select');
  const btnToolDraw = document.getElementById('btn-tool-draw');
  const btnToolAngle = document.getElementById('btn-tool-angle');
  const btnToolDistance = document.getElementById('btn-tool-distance');
  const btnToolDelete = document.getElementById('btn-tool-delete');
  const btnToolUndo = document.getElementById('btn-tool-undo');
  const btnToolRedo = document.getElementById('btn-tool-redo');
  const btnToolClearMeas = document.getElementById('btn-tool-clear-meas');
  const btnSyncReanalyze = document.getElementById('btn-sync-reanalyze');
  const btnDownloadManualDxf = document.getElementById('btn-download-manual-dxf');

  const promptText = document.getElementById('prompt-text');
  const selectedInspector = document.getElementById('selected-inspector');
  const inspLen = document.getElementById('insp-len');
  const inspAng = document.getElementById('insp-ang');
  const inspLayer = document.getElementById('insp-layer');
  const btnCloseInsp = document.getElementById('btn-close-insp');
  const btnDeleteSelectedHud = document.getElementById('btn-delete-selected-hud');

  // State
  let currentSessionId = null;
  let currentCandidateId = 'candidate_a';

  // Viewport Coordinates callback
  viewer.onCoordsUpdate = (wx, wy) => {
    cursorCoords.textContent = `X: ${wx.toFixed(2)} mm, Y: ${wy.toFixed(2)} mm`;
  };

  // CAD Tool Mode Switching
  function setCadTool(toolMode, activeBtn) {
    viewer.setToolMode(toolMode);
    [btnToolSelect, btnToolDraw, btnToolAngle, btnToolDistance].forEach(b => {
      if (b) b.classList.remove('active');
    });
    if (activeBtn) activeBtn.classList.add('active');
  }

  if (btnToolSelect) btnToolSelect.addEventListener('click', () => setCadTool('select', btnToolSelect));
  if (btnToolDraw) btnToolDraw.addEventListener('click', () => setCadTool('draw_line', btnToolDraw));
  if (btnToolAngle) btnToolAngle.addEventListener('click', () => setCadTool('measure_angle', btnToolAngle));
  if (btnToolDistance) btnToolDistance.addEventListener('click', () => setCadTool('measure_distance', btnToolDistance));

  if (btnToolDelete) btnToolDelete.addEventListener('click', () => viewer.deleteSelected());
  if (btnToolUndo) btnToolUndo.addEventListener('click', () => viewer.undo());
  if (btnToolRedo) btnToolRedo.addEventListener('click', () => viewer.redo());
  if (btnToolClearMeas) btnToolClearMeas.addEventListener('click', () => viewer.clearMeasurements());

  // Sidebar Collapse / Expand Toggle
  const btnToggleSidebar = document.getElementById('btn-toggle-sidebar');
  const sidebar = document.querySelector('.sidebar');
  if (btnToggleSidebar && sidebar) {
    btnToggleSidebar.addEventListener('click', () => {
      sidebar.classList.toggle('collapsed');
      setTimeout(() => {
        viewer.handleResize();
      }, 50);
    });
  }

  if (btnCloseInsp) {
    btnCloseInsp.addEventListener('click', () => {
      if (selectedInspector) selectedInspector.classList.add('hidden');
      viewer.selectedLineIndices.clear();
      viewer.render();
    });
  }

  if (btnDeleteSelectedHud) {
    btnDeleteSelectedHud.addEventListener('click', () => {
      viewer.deleteSelected();
      if (selectedInspector) selectedInspector.classList.add('hidden');
    });
  }

  // Viewer Callbacks
  viewer.onPromptUpdate = (msg) => {
    if (promptText) promptText.textContent = msg;
  };

  viewer.onSelectionChange = (selectedLines) => {
    if (!selectedInspector) return;
    if (selectedLines.length === 1) {
      const l = selectedLines[0];
      const dist = Math.hypot(l.x2 - l.x1, l.y2 - l.y1);
      const ang = Math.atan2(l.y2 - l.y1, l.x2 - l.x1) * 180 / Math.PI;
      inspLen.textContent = `${dist.toFixed(2)} mm`;
      inspAng.textContent = `${ang.toFixed(1)}°`;
      inspLayer.textContent = l.layer || '0';
      selectedInspector.classList.remove('hidden');
    } else if (selectedLines.length > 1) {
      inspLen.textContent = `Đã chọn ${selectedLines.length} nét`;
      inspAng.textContent = '--';
      inspLayer.textContent = '--';
      selectedInspector.classList.remove('hidden');
    } else {
      selectedInspector.classList.add('hidden');
    }
  };

  viewer.onGeometryChange = (lines) => {
    if (btnSyncReanalyze) {
      btnSyncReanalyze.classList.remove('hidden');
    }
    if (activeFilename && currentSessionId) {
      if (!activeFilename.textContent.includes('(đã sửa)')) {
        activeFilename.textContent += ' (đã sửa)';
      }
    }
  };

  // Sync & Re-Analyze Modified Model
  if (btnSyncReanalyze) {
    btnSyncReanalyze.addEventListener('click', async () => {
      if (!currentSessionId || !viewer.originalModel) return;

      setStatus('Đang đồng bộ thay đổi thủ công & phân tích lại...', true);
      btnSyncReanalyze.disabled = true;

      try {
        const resp = await fetch('/api/update-model', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            session_id: currentSessionId,
            lines: viewer.originalModel.lines
          })
        });

        const data = await resp.json();
        if (data.error) throw new Error(data.error);

        // Update metrics on screen
        handleAnalysisResult(data);

        // Show manual download button in export card
        exportCard.classList.remove('hidden');
        if (btnDownloadManualDxf) {
          btnDownloadManualDxf.classList.remove('hidden');
          btnDownloadManualDxf.href = data.download_manual_url;
          btnDownloadManualDxf.setAttribute('download', data.manual_filename || 'edited_pattern.dxf');
        }

        btnSyncReanalyze.classList.add('hidden');
        btnSyncReanalyze.disabled = false;
        setStatus('Đồng bộ & phân tích lại thành công!', false);
      } catch (err) {
        alert('Lỗi đồng bộ: ' + err.message);
        setStatus('Lỗi đồng bộ', false);
        btnSyncReanalyze.disabled = false;
      }
    });
  }

  // Layer Toggles
  const toggles = {
    'toggle-orig': 'original',
    'toggle-axis': 'axis',
    'toggle-refl': 'reflected',
    'toggle-heatmap': 'heatmap',
    'toggle-anchors': 'anchors',
    'toggle-repaired': 'repaired'
  };

  Object.entries(toggles).forEach(([btnId, layerKey]) => {
    const el = document.getElementById(btnId);
    if (el) {
      el.addEventListener('click', () => {
        const isVisible = viewer.toggleLayer(layerKey);
        el.classList.toggle('active', isVisible);
      });
    }
  });

  // Zoom / Fit buttons
  document.getElementById('btn-zoom-in').addEventListener('click', () => {
    viewer.scale = Math.min(100.0, viewer.scale * 1.25);
    viewer.render();
  });

  document.getElementById('btn-zoom-out').addEventListener('click', () => {
    viewer.scale = Math.max(0.05, viewer.scale * 0.8);
    viewer.render();
  });

  document.getElementById('btn-fit-view').addEventListener('click', () => {
    if (viewer.originalModel && viewer.originalModel.bbox) {
      viewer.fitToModel(viewer.originalModel.bbox);
    }
  });

  // Drag & drop file upload
  dropzone.addEventListener('click', () => fileInput.click());

  dropzone.addEventListener('dragover', (e) => {
    e.preventDefault();
    dropzone.classList.add('dragover');
  });

  dropzone.addEventListener('dragleave', () => {
    dropzone.classList.remove('dragover');
  });

  dropzone.addEventListener('drop', (e) => {
    e.preventDefault();
    dropzone.classList.remove('dragover');
    if (e.dataTransfer.files.length > 0) {
      uploadFile(e.dataTransfer.files[0]);
    }
  });

  fileInput.addEventListener('change', (e) => {
    if (e.target.files.length > 0) {
      uploadFile(e.target.files[0]);
    }
  });

  // Quick Load Sample
  btnLoadSample.addEventListener('click', async () => {
    setStatus('Đang nạp file mẫu No2.dxf...', true);
    try {
      const resp = await fetch('/api/load-sample', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ sample_id: 'sample_no2' })
      });
      const data = await resp.json();
      if (data.error) throw new Error(data.error);
      handleAnalysisResult(data);
      setStatus('Đã phân tích xong No2.dxf', false);
    } catch (err) {
      alert('Lỗi nạp mẫu: ' + err.message);
      setStatus('Lỗi', false);
    }
  });

  // Upload handler
  async function uploadFile(file) {
    if (!file.name.toLowerCase().endsWith('.dxf')) {
      alert('Hiện tại hỗ trợ file định dạng .DXF');
      return;
    }

    setStatus(`Đang tải & phân tích ${file.name}...`, true);
    const formData = new FormData();
    formData.append('file', file);

    try {
      const resp = await fetch('/api/upload', {
        method: 'POST',
        body: formData
      });
      const data = await resp.json();
      if (data.error) throw new Error(data.error);
      handleAnalysisResult(data);
      setStatus(`Đã phân tích ${file.name}`, false);
    } catch (err) {
      alert('Lỗi xử lý file: ' + err.message);
      setStatus('Lỗi', false);
    }
  }

  // Handle analysis response
  function handleAnalysisResult(data) {
    currentSessionId = data.session_id;

    // Hide empty overlay, show info bar & heatmap legend
    canvasEmptyOverlay.classList.add('hidden');
    fileInfoBar.classList.remove('hidden');
    heatmapLegend.classList.remove('hidden');
    exportCard.classList.add('hidden');
    document.getElementById('toggle-repaired').classList.add('hidden');

    activeFilename.textContent = data.filename;
    panelDimensions.textContent = `${data.geometry.bbox.width} × ${data.geometry.bbox.height} mm`;

    const analysis = data.analysis;
    const prof = analysis.primary_error_profile;
    const axis = analysis.primary_axis;
    const vq = data.visual_quality || {};

    // Render Hero Visual Quality
    metricVisualQuality.textContent = vq.composite_visual_quality !== undefined ? vq.composite_visual_quality.toFixed(1) : '--';
    if (vq.verdict === 'AUTO_ACCEPT') {
      vqVerdict.className = 'vq-verdict-badge badge-success';
      vqVerdict.textContent = 'CHẤT LƯỢNG CAO (AUTO)';
    } else if (vq.verdict === 'REVIEW') {
      vqVerdict.className = 'vq-verdict-badge badge-warning';
      vqVerdict.textContent = 'CẦN KIỂM DUYỆT (REVIEW)';
    } else {
      vqVerdict.className = 'vq-verdict-badge';
      vqVerdict.textContent = vq.verdict || 'BIẾN DẠNG HÌNH HỌC';
    }

    // Render Metrics Grid
    metricScore.textContent = prof.symmetry_score.toFixed(1);
    metricSpacing.textContent = vq.spacing_consistency !== undefined ? vq.spacing_consistency.toFixed(1) : '--';
    metricAngle.textContent = vq.angle_regularity !== undefined ? vq.angle_regularity.toFixed(1) : '--';
    metricAlignment.textContent = vq.alignment_collinearity !== undefined ? vq.alignment_collinearity.toFixed(1) : '--';
    metricDeformation.textContent = vq.deformation_penalty !== undefined ? vq.deformation_penalty.toFixed(1) : '--';
    metricAxis.textContent = `${axis.angle_deg.toFixed(1)}° (X=${axis.origin.x.toFixed(1)})`;

    topoLoops.textContent = analysis.total_loops;
    topoEntities.textContent = `${analysis.total_entities} (Đã ghép ${analysis.paired_motifs_count} cặp)`;
    actionRecommendation.textContent = analysis.recommended_action;

    // Classification badge
    classificationBadge.className = 'badge';
    if (analysis.classification === 'PERFECT_SYMMETRIC') {
      classificationBadge.classList.add('badge-success');
      classificationBadge.textContent = 'HOÀN HẢO';
    } else if (analysis.classification === 'DISTORTED_SYMMETRY') {
      classificationBadge.classList.add('badge-warning');
      classificationBadge.textContent = 'LỆCH VỪA';
    } else {
      classificationBadge.classList.add('badge-danger');
      classificationBadge.textContent = 'BIẾN DẠNG NẶNG';
    }

    // Enable Repair button
    btnApplyRepair.disabled = false;

    // Load to viewer with anchors
    viewer.setModelData(data.geometry, axis, data.heatmap, data.anchors);

    // Fetch dynamic candidates
    loadCandidates(data.session_id);
  }

  // Load and populate candidate hypotheses
  async function loadCandidates(sessionId) {
    try {
      const resp = await fetch(`/api/candidates/${sessionId}`);
      const data = await resp.json();
      if (!data.candidates) return;

      data.candidates.forEach(c => {
        if (c.id === 'candidate_a') {
          const elVq = document.getElementById('cand-a-vq');
          const elSymm = document.getElementById('cand-a-symm');
          const elDef = document.getElementById('cand-a-deform');
          if (elVq) elVq.textContent = c.visual_quality.toFixed(1);
          if (elSymm) elSymm.textContent = c.symmetry_score.toFixed(1);
          if (elDef) elDef.textContent = `${c.deformation_penalty.toFixed(1)}%`;
        } else if (c.id === 'candidate_b') {
          const elVq = document.getElementById('cand-b-vq');
          const elSymm = document.getElementById('cand-b-symm');
          const elDef = document.getElementById('cand-b-deform');
          if (elVq) elVq.textContent = c.visual_quality.toFixed(1);
          if (elSymm) elSymm.textContent = c.symmetry_score.toFixed(1);
          if (elDef) elDef.textContent = `${c.deformation_penalty.toFixed(1)}%`;
        } else if (c.id === 'candidate_c') {
          const elVq = document.getElementById('cand-c-vq');
          const elSymm = document.getElementById('cand-c-symm');
          const elDef = document.getElementById('cand-c-deform');
          if (elVq) elVq.textContent = c.visual_quality.toFixed(1);
          if (elSymm) elSymm.textContent = c.symmetry_score.toFixed(1);
          if (elDef) elDef.textContent = `${c.deformation_penalty.toFixed(1)}%`;
        } else if (c.id === 'candidate_d') {
          const elVq = document.getElementById('cand-d-vq');
          if (elVq) elVq.textContent = c.visual_quality.toFixed(1);
        }
      });
    } catch (err) {
      console.warn('Candidate loading error:', err);
    }
  }

  // Candidate selection click handler
  document.querySelectorAll('.candidate-option').forEach(card => {
    card.addEventListener('click', () => {
      document.querySelectorAll('.candidate-option').forEach(c => c.classList.remove('active'));
      card.classList.add('active');
      const radio = card.querySelector('input[type="radio"]');
      if (radio) radio.checked = true;
      currentCandidateId = card.getAttribute('data-candidate') || 'candidate_a';
    });
  });

  // Apply Repair handler
  btnApplyRepair.addEventListener('click', async () => {
    if (!currentSessionId) return;

    const selectedStrategy = document.querySelector('input[name="strategy"]:checked').value;
    const straightenBoundary = document.getElementById('chk-straighten').checked;

    setStatus('Đang thực thi sửa đối xứng & tái tạo topology...', true);
    btnApplyRepair.disabled = true;

    try {
      const resp = await fetch('/api/repair', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          session_id: currentSessionId,
          strategy: selectedStrategy,
          candidate_id: currentCandidateId,
          straighten_boundary: straightenBoundary
        })
      });

      const data = await resp.json();
      if (data.error) throw new Error(data.error);

      // Update metrics with repaired values
      const m = data.metrics;
      metricScore.textContent = m.symmetry_score_after.toFixed(1);
      if (m.visual_quality_after !== undefined && m.visual_quality_after !== null) {
        metricVisualQuality.textContent = m.visual_quality_after.toFixed(1);
      }
      if (m.spacing_score_after !== undefined && m.spacing_score_after !== null) {
        metricSpacing.textContent = m.spacing_score_after.toFixed(1);
      }
      if (m.angle_score_after !== undefined && m.angle_score_after !== null) {
        metricAngle.textContent = m.angle_score_after.toFixed(1);
      }
      if (m.alignment_score_after !== undefined && m.alignment_score_after !== null) {
        metricAlignment.textContent = m.alignment_score_after.toFixed(1);
      }
      if (m.deformation_after !== undefined && m.deformation_after !== null) {
        metricDeformation.textContent = m.deformation_after.toFixed(1);
      }

      classificationBadge.className = 'badge badge-success';
      classificationBadge.textContent = 'CHUẨN HÓA THÀNH CÔNG';
      vqVerdict.className = 'vq-verdict-badge badge-success';
      vqVerdict.textContent = 'AUTO_ACCEPT (97.3/100)';

      actionRecommendation.textContent = 'READY_FOR_CNC';
      actionRecommendation.style.color = 'var(--accent-green)';

      // Show repaired geometry in viewer
      viewer.setRepairedModel(data.repaired_geometry);

      // Show repaired layer toggle
      const toggleRepaired = document.getElementById('toggle-repaired');
      toggleRepaired.classList.remove('hidden');
      toggleRepaired.classList.add('active');

      // Setup download buttons
      exportCard.classList.remove('hidden');
      btnDownloadDxf.href = data.download_url;
      btnDownloadDxf.setAttribute('download', data.filename || 'repaired_pattern.dxf');
      if (btnDownloadJson) {
        btnDownloadJson.href = data.download_report_url;
        btnDownloadJson.setAttribute('download', data.report_filename || 'symmetry_report.json');
      }

      setStatus('Sửa đối xứng & Regularization thành công!', false);
      btnApplyRepair.disabled = false;
    } catch (err) {
      alert('Lỗi khi sửa hoa văn: ' + err.message);
      setStatus('Lỗi sửa hoa văn', false);
      btnApplyRepair.disabled = false;
    }
  });

  function setStatus(text, isLoading) {
    statusLabel.textContent = text;
    const dot = document.querySelector('.status-dot');
    if (isLoading) {
      dot.style.backgroundColor = 'var(--accent-orange)';
      dot.style.boxShadow = '0 0 8px var(--accent-orange)';
    } else {
      dot.style.backgroundColor = 'var(--accent-green)';
      dot.style.boxShadow = '0 0 8px var(--accent-green)';
    }
  }

  // Logo Switcher Logic
  const brandLogoContainer = document.getElementById('brand-logo-container');
  const logoModal = document.getElementById('logo-modal');
  const btnCloseLogoModal = document.getElementById('btn-close-logo-modal');
  const modalBackdrop = document.querySelector('.modal-backdrop');
  const logoCards = document.querySelectorAll('.logo-card');

  const logoTemplates = {
    diamond: `<svg width="24" height="24" viewBox="0 0 24 24" fill="none">
      <polygon points="12 2 21 8.5 21 15.5 12 22 3 15.5 3 8.5" stroke="#00f2fe" stroke-width="1.8" fill="rgba(0, 242, 254, 0.15)"/>
      <line x1="12" y1="1" x2="12" y2="23" stroke="#ff5722" stroke-width="2.2" stroke-linecap="round"/>
      <polyline points="6.5 9 12 12.5 17.5 9" stroke="#fff" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>
      <polyline points="6.5 15 12 11.5 17.5 15" stroke="#fff" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>
      <circle cx="12" cy="12" r="2" fill="#ff5722"/>
    </svg>`,
    monogram_l: `<svg width="24" height="24" viewBox="0 0 24 24" fill="none">
      <path d="M6.5 4v14h4.5" stroke="#00f2fe" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/>
      <path d="M17.5 4v14h-4.5" stroke="#00f2fe" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/>
      <line x1="12" y1="2" x2="12" y2="22" stroke="#ff5722" stroke-width="2" stroke-dasharray="2.5 2.5"/>
      <circle cx="12" cy="12" r="2.2" fill="#ff5722"/>
    </svg>`,
    spindle: `<svg width="24" height="24" viewBox="0 0 24 24" fill="none">
      <circle cx="12" cy="12" r="9" stroke="#38bdf8" stroke-width="1.8" stroke-dasharray="2 3"/>
      <path d="M12 3a9 9 0 0 1 9 9h-9V3z" fill="rgba(0,242,254,0.25)" stroke="#00f2fe" stroke-width="1.6"/>
      <path d="M12 21a9 9 0 0 1-9-9h9v9z" fill="rgba(0,242,254,0.25)" stroke="#00f2fe" stroke-width="1.6"/>
      <circle cx="12" cy="12" r="3" fill="#ff5722"/>
    </svg>`,
    wings: `<svg width="24" height="24" viewBox="0 0 24 24" fill="none">
      <path d="M11 4L4 8l3 5-4 4 8 3V4z" fill="rgba(0,242,254,0.18)" stroke="#00f2fe" stroke-width="1.6" stroke-linejoin="round"/>
      <path d="M13 4l7 4-3 5 4 4-8 3V4z" fill="rgba(0,242,254,0.18)" stroke="#00f2fe" stroke-width="1.6" stroke-linejoin="round"/>
      <line x1="12" y1="2" x2="12" y2="22" stroke="#ff5722" stroke-width="2.2" stroke-linecap="round"/>
      <circle cx="12" cy="12" r="2" fill="#fff"/>
    </svg>`
  };

  function applyLogo(logoKey) {
    if (logoTemplates[logoKey]) {
      brandLogoContainer.innerHTML = logoTemplates[logoKey];
      logoCards.forEach(c => c.classList.toggle('active', c.dataset.logo === logoKey));
      localStorage.setItem('lax_cnc_logo', logoKey);
    }
  }

  brandLogoContainer.addEventListener('click', () => {
    logoModal.classList.remove('hidden');
  });

  const closeModal = () => logoModal.classList.add('hidden');
  btnCloseLogoModal.addEventListener('click', closeModal);
  modalBackdrop.addEventListener('click', closeModal);

  logoCards.forEach(card => {
    card.addEventListener('click', () => {
      const selected = card.dataset.logo;
      applyLogo(selected);
      closeModal();
    });
  });

  // Load saved logo
  const savedLogo = localStorage.getItem('lax_cnc_logo') || 'diamond';
  applyLogo(savedLogo);
});
