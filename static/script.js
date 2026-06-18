
let currentStudies = [];
let allStudies = []; // Store full dataset
let currentSort = { field: null, direction: 'asc' };
let useDownstream = false;
let lastHeadlineData = null; // Store original RR results for transformation

// Global Error Handler for Debugging
window.onerror = function (msg, url, line, col, error) {
    console.error("Global Error:", msg, "at", url, ":", line);
    const errorMsg = document.getElementById('error-message');
    if (errorMsg) {
        errorMsg.textContent = `JavaScript Error: ${msg} (at line ${line})`;
        errorMsg.classList.remove('hidden');
    }
};

document.addEventListener('DOMContentLoaded', async () => {
    console.log("MetaFemina JS Loaded - v1.5 (Robust)");

    // Elements
    const elements = {
        outcome: document.getElementById('outcome'),
        stageFilterContainer: document.getElementById('stage-filter-container'),
        exposure: document.getElementById('exposure'),
        exposureOptions: document.getElementById('exposure-options'),
        disease: document.getElementById('disease'),
        excludeMeta: document.getElementById('exclude-meta'),
        model: document.getElementById('model'),
        analyzeBtn: document.getElementById('analyze-btn'),
        refreshBtn: document.getElementById('refresh-btn'),
        updateBtn: document.getElementById('update-btn'),
        loading: document.getElementById('loading'),
        results: document.getElementById('results'),
        errorMsg: document.getElementById('error-message'),
        filterTiming: document.getElementById('filter-timing'),
        filterMinCases: document.getElementById('filter-min-cases'),
        filterStage: document.getElementById('filter-stage'),
        filterQuality: document.getElementById('filter-quality'),
        filterMeasure: document.getElementById('filter-measure'),
        filterExposureType: document.getElementById('filter-exposure-type'),
        selectAllCheckbox: document.getElementById('select-all-checkbox'),
        selectAllBtn: document.getElementById('select-all-btn'),
        deselectAllBtn: document.getElementById('deselect-all-btn'),
        studiesTbody: document.querySelector('#studies-table tbody'),
        forestPlot: document.getElementById('forest-plot'),
        funnelPlot: document.getElementById('funnel-plot'),
        headlineResult: document.getElementById('headline-result'),
        pooledEs: document.getElementById('pooled-es'),
        pooledCi: document.getElementById('pooled-ci'),
        interpretation: document.getElementById('interpretation'),
        lastUpdated: document.getElementById('last-updated'),
        heterogeneityStats: document.getElementById('heterogeneity-stats'),
        valI2: document.getElementById('val-i2'),
        valTau2: document.getElementById('val-tau2'),
        valEggers: document.getElementById('val-eggers'),
        funnelInterpretation: document.getElementById('funnel-interpretation'),
        resultsInterpretation: document.getElementById('results-interpretation'),
        influenceSection: document.getElementById('influence-section'),
        baujatPlot: document.getElementById('baujat-plot'),
        looTbody: document.getElementById('loo-tbody'),
        synonymsBox: document.getElementById('synonyms-box'),
        synonymsPills: document.getElementById('synonyms-pills'),
        displayMeasure: document.getElementById('display-measure'),
        pooledLabel: document.getElementById('pooled-label'),
        pooledPowerAnalysis: document.getElementById('pooled-power-analysis'),
        pooledIncidence: document.getElementById('pooled-incidence'),
        pooledPowerEsText: document.getElementById('pooled-power-es-text'),
        pooledPowerNTotal: document.getElementById('pooled-power-n-total'),
        pooledPowerCases: document.getElementById('pooled-power-cases'),
        powerAlpha: document.getElementById('power-alpha'),
        powerValue: document.getElementById('power-value'),
        powerSides: document.getElementById('power-sides'),
        powerEffect: document.getElementById('power-effect'),
        powerArms: document.getElementById('power-arms'),
        powerTextDisplay: document.getElementById('power-text-display'),
        alphaTextDisplay: document.getElementById('alpha-text-display'),
        sidesTextDisplay: document.getElementById('sides-text-display'),
        piContainer: document.getElementById('pi-container'),
        pooledPi: document.getElementById('pooled-pi'),
        pooledPowerPerGroup: document.getElementById('pooled-power-per-group')
    };

    // Verify critical elements
    for (const [name, el] of Object.entries(elements)) {
        if (!el && !['stageFilterContainer', 'funnelPlot'].includes(name)) {
            console.warn(`Critical element missing: ${name}`);
        }
    }

    // Initialize Last Updated
    updateLastUpdated();

    // Toggle Stage Filter
    function toggleStageFilter() {
        if (!elements.outcome || !elements.stageFilterContainer) return;
        const outcome = elements.outcome.value;
        if (outcome === 'Incidence') {
            elements.stageFilterContainer.classList.add('hidden');
            elements.stageFilterContainer.style.display = 'none';
        } else {
            elements.stageFilterContainer.classList.remove('hidden');
            elements.stageFilterContainer.style.display = 'block';
        }
    }

    if (elements.outcome) {
        elements.outcome.addEventListener('change', toggleStageFilter);
        toggleStageFilter();
    }

    // Exposure Input Handling
    if (elements.exposure) {
        elements.exposure.value = "Vitamin A"; // Default as requested

        let exposures = [];
        let synonymsMap = {}; // { "soy": {core: "...", downstream: "..."}, ... }
        let isReadOnly = false;
        let cachedExposures = [];

        function safePathComponent(val) {
            return (val || '').toLowerCase()
                .replace(/[^a-z0-9._-]/g, '_')
                .replace(/_+/g, '_')
                .replace(/(^_|_$)/g, '');
        }

        try {
            const [expRes, synRes, configRes] = await Promise.all([
                fetch('/static/exposures.json'),
                fetch('/api/synonyms'),
                fetch('/api/config')
            ]);
            if (expRes.ok) exposures = await expRes.json();
            if (synRes.ok) synonymsMap = await synRes.json();
            if (configRes.ok) {
                const configData = await configRes.json();
                isReadOnly = configData.read_only;
                cachedExposures = configData.cached_exposures;
            }
        } catch (e) {
            console.error("Error fetching exposures/synonyms/config:", e);
        }

        if (isReadOnly) {
            // Filter exposures list to only include those present in cachedExposures
            exposures = exposures.filter(e => {
                const safeE = safePathComponent(e);
                return cachedExposures.some(cached => {
                    const safeCached = safePathComponent(cached);
                    return safeE === safeCached || safeCached.includes(safeE) || safeE.includes(safeCached);
                });
            });

            // Hide refresh button
            if (elements.refreshBtn) {
                elements.refreshBtn.style.display = 'none';
            }

            // Show Read-Only banner
            const banner = document.getElementById('read-only-banner');
            if (banner) banner.classList.remove('hidden');


        }

        // Show synonyms for current exposure value on load
        updateSynonymsBox(elements.exposure.value);

        // Toggle listener
        const downstreamToggle = document.getElementById('use-downstream-toggle');
        if (downstreamToggle) {
            downstreamToggle.addEventListener('change', () => {
                useDownstream = downstreamToggle.checked;
                updateSynonymsBox(elements.exposure.value);
            });
        }

        function getSynEntry(val) {
            const lc = (val || '').toLowerCase().trim();
            // 1. Direct match with key
            let matchKey = Object.keys(synonymsMap).find(k => k.toLowerCase() === lc);
            
            // 2. Resolve to canonical key if the value is listed inside any core synonym list
            if (!matchKey) {
                matchKey = Object.keys(synonymsMap).find(k => {
                    const entry = synonymsMap[k];
                    if (!entry || !entry.core) return false;
                    const coreTerms = entry.core.split(',').map(t => t.trim().toLowerCase());
                    return coreTerms.includes(lc);
                });
            }
            
            // 3. Fallback to substring matching
            if (!matchKey) {
                matchKey = Object.keys(synonymsMap).find(k => lc.includes(k.toLowerCase()) || k.toLowerCase().includes(lc));
            }
            
            if (!matchKey) return null;
            const entry = synonymsMap[matchKey];
            // Handle both legacy flat string and new dict format
            if (typeof entry === 'string') return { core: entry, downstream: '' };
            return entry;
        }

        function cleanAndNormalizeTerms(terms, val) {
            const seen = new Set();
            const result = [];
            
            // Helper to clean apostrophes and trim
            const clean = (s) => (s || '').replace(/[’â€™Ã¢â‚¬â„¢]/g, "'").trim().toLowerCase();
            const valClean = clean(val);
            
            terms.forEach(term => {
                const cleaned = clean(term);
                if (!cleaned || cleaned === valClean || seen.has(cleaned)) {
                    return;
                }
                seen.add(cleaned);
                
                // Capitalize the term nicely for display
                let formatted = term.split(' ').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ');
                
                // Keep some special acronyms uppercase
                if (formatted.toLowerCase() === '5-htp') formatted = '5-HTP';
                else if (formatted.toLowerCase() === 'bcaas') formatted = 'BCAAs';
                else if (formatted.toLowerCase() === 'cbd') formatted = 'CBD';
                else if (formatted.toLowerCase() === 'hmb') formatted = 'HMB';
                else if (formatted.toLowerCase() === 'msm') formatted = 'MSM';
                else if (formatted.toLowerCase() === 'nac') formatted = 'NAC';
                
                result.push(formatted);
            });
            
            return result;
        }

        function updateSynonymsBox(val) {
            if (!elements.synonymsBox || !elements.synonymsPills) return;
            const entry = getSynEntry(val);
            if (!entry && !val) {
                elements.synonymsBox.style.display = 'none';
                return;
            }
            
            const primaryVal = val.trim();
            const rawSynonyms = entry && entry.core ? entry.core.split(',') : [];
            const cleanedSynonyms = cleanAndNormalizeTerms(rawSynonyms, primaryVal);
            const coreTerms = [primaryVal].concat(cleanedSynonyms);
            
            const rawDownstream = entry && entry.downstream ? entry.downstream.split(',') : [];
            const downstreamTerms = cleanAndNormalizeTerms(rawDownstream, primaryVal);

            const corePills = coreTerms.map((t, i) => `<span style="
                display:inline-block; padding: 3px 10px; border-radius: 20px;
                font-size: 0.8rem; font-weight: ${i === 0 ? 700 : 400};
                background: rgba(233,30,99,${i === 0 ? '0.15' : '0.06'});
                border: 1px solid rgba(233,30,99,${i === 0 ? '0.45' : '0.2'});
                color: #333;
            ">${t}</span>`).join('');

            const downstreamPills = downstreamTerms.map(t => `<span style="
                display:inline-block; padding: 3px 10px; border-radius: 20px;
                font-size: 0.8rem; font-weight: 400;
                background: ${useDownstream ? 'rgba(100,100,100,0.07)' : 'rgba(200,200,200,0.07)'};
                border: 1px solid rgba(150,150,150,${useDownstream ? '0.35' : '0.15'});
                color: ${useDownstream ? '#555' : '#aaa'};
                text-decoration: ${useDownstream ? 'none' : 'line-through'};
            ">${t}</span>`).join('');

            elements.synonymsPills.innerHTML = corePills + (downstreamPills ? '<span style="font-size:0.7rem;color:#999;align-self:center;padding:0 4px;">|</span>' + downstreamPills : '');
            elements.synonymsBox.style.display = (coreTerms.length > 0 || downstreamTerms.length > 0) ? 'block' : 'none';
        }

        function getDropdownMatches(val) {
            if (!val) return exposures.map(e => ({ label: e, value: e, hint: null }));

            const lc = val.toLowerCase();
            const results = [];
            const seen = new Set();

            exposures.forEach(exp => {
                if (exp.toLowerCase().includes(lc)) {
                    results.push({ label: exp, value: exp, hint: null });
                    seen.add(exp.toLowerCase());
                }
            });

            // Also match against synonyms
            Object.entries(synonymsMap).forEach(([key, entry]) => {
                if (!entry) return;
                const synStr = typeof entry === 'string' ? entry : [entry.core, entry.downstream].filter(Boolean).join(',');
                const syns = synStr.split(',').map(s => s.trim()).filter(Boolean);
                const matchedSyn = syns.find(s => s.toLowerCase().includes(lc));
                if (!matchedSyn) return;

                // Find the canonical exposure name (case-insensitive key match)
                const canonical = exposures.find(e => e.toLowerCase() === key.toLowerCase()) || key;
                if (!seen.has(canonical.toLowerCase())) {
                    results.push({ label: canonical, value: canonical, hint: matchedSyn });
                    seen.add(canonical.toLowerCase());
                }
            });

            return results;
        }

        elements.exposure.addEventListener('input', () => {
            const val = elements.exposure.value;
            updateSynonymsBox(val);
            const matches = getDropdownMatches(val.toLowerCase ? val : val);

            if (elements.exposureOptions) {
                elements.exposureOptions.innerHTML = '';
                if (matches.length > 0) {
                    matches.forEach(match => {
                        const div = document.createElement('div');
                        if (match.hint) {
                            div.innerHTML = `${match.label} <span style="font-size:0.8em; opacity:0.65; font-style:italic;">— ${match.hint}</span>`;
                        } else {
                            div.textContent = match.label;
                        }
                        div.addEventListener('click', () => {
                            elements.exposure.value = match.value;
                            elements.exposureOptions.style.display = 'none';
                            updateSynonymsBox(match.value);
                        });
                        elements.exposureOptions.appendChild(div);
                    });
                    elements.exposureOptions.style.display = 'block';
                } else {
                    elements.exposureOptions.style.display = 'none';
                }
            }
        });

        elements.exposure.addEventListener('focus', () => {
            elements.exposure.dispatchEvent(new Event('input'));
        });

        document.addEventListener('click', (e) => {
            if (elements.exposureOptions && !elements.exposure.contains(e.target) && !elements.exposureOptions.contains(e.target)) {
                elements.exposureOptions.style.display = 'none';
            }
        });
    }

    // Select All Logic (Fixed Nesting)
    if (elements.selectAllCheckbox) {
        elements.selectAllCheckbox.addEventListener('change', (e) => {
            const checkboxes = document.querySelectorAll('.study-checkbox');
            checkboxes.forEach(cb => cb.checked = e.target.checked);
        });
    }

    // Delegated Change Listener for Study Checkboxes
    document.addEventListener('change', (e) => {
        if (e.target && e.target.classList.contains('study-checkbox')) {
            if (elements.selectAllCheckbox) {
                const checkboxes = document.querySelectorAll('.study-checkbox');
                const checkedCount = Array.from(checkboxes).filter(cb => cb.checked).length;
                elements.selectAllCheckbox.checked = checkedCount === checkboxes.length;
                elements.selectAllCheckbox.indeterminate = checkedCount > 0 && checkedCount < checkboxes.length;
            }
        }
    });

    // Select All / Deselect All Buttons
    if (elements.selectAllBtn) {
        elements.selectAllBtn.addEventListener('click', () => {
            const checkboxes = document.querySelectorAll('.study-checkbox');
            checkboxes.forEach(cb => cb.checked = true);
            if (elements.selectAllCheckbox) {
                elements.selectAllCheckbox.checked = true;
                elements.selectAllCheckbox.indeterminate = false;
            }
        });
    }
    if (elements.deselectAllBtn) {
        elements.deselectAllBtn.addEventListener('click', () => {
            const checkboxes = document.querySelectorAll('.study-checkbox');
            checkboxes.forEach(cb => cb.checked = false);
            if (elements.selectAllCheckbox) {
                elements.selectAllCheckbox.checked = false;
                elements.selectAllCheckbox.indeterminate = false;
            }
        });
    }

    // Filtering
    if (elements.filterTiming) elements.filterTiming.addEventListener('change', applyFilters);
    if (elements.filterMinCases) elements.filterMinCases.addEventListener('input', renderStudiesTable);
    if (elements.filterStage) elements.filterStage.addEventListener('change', applyFilters);
    if (elements.filterQuality) elements.filterQuality.addEventListener('change', applyFilters);
    if (elements.filterMeasure) elements.filterMeasure.addEventListener('change', applyFilters);
    if (elements.filterExposureType) {
        elements.filterExposureType.addEventListener('change', () => {
            applyFilters();
            if (elements.updateBtn) {
                elements.updateBtn.click();
            }
        });
    }

    function applyFilters() {
        const timing = elements.filterTiming ? elements.filterTiming.value : 'All';
        const stage = elements.filterStage ? elements.filterStage.value : 'All';
        const quality = elements.filterQuality ? elements.filterQuality.value : 'All';
        const measure = elements.filterMeasure ? elements.filterMeasure.value : 'All';
        const exposureType = elements.filterExposureType ? elements.filterExposureType.value : 'Anything';

        currentStudies = allStudies.filter(study => {
            if (timing !== 'All') {
                if (timing === 'Clinical Trials') {
                    if (study.Design !== 'Clinical Trials') return false;
                } else if (study.Timing !== timing) {
                    return false;
                }
            }
            if (stage !== 'All' && study.Stage !== stage) return false;
            if (quality === 'Moderate+') {
                const score = (study['Quality Score'] || 'Fair');
                if (score !== 'Good' && score !== 'Moderate') return false;
            } else if (quality !== 'All' && quality !== 'Fair+' && (study['Quality Score'] || 'Fair') !== quality) return false;
            if (measure !== 'All' && (study['Effect Type'] || '').toUpperCase() !== measure) return false;
            
            const studyExpType = study.exposure_measurement_type || 'unclear';
            if (exposureType === 'Dietary intake only') {
                if (studyExpType !== 'dietary_intake') return false;
            } else if (exposureType === 'Human biospecimen only') {
                if (studyExpType !== 'human_biospecimen') return false;
            }
            return true;
        });

        renderStudiesTable();
    }

    function updateBaselineIncidence() {
        if (!elements.disease || !elements.pooledIncidence) return;
        const disease = elements.disease.value.toLowerCase();
        let val = 13.0; // default/breast cancer
        if (disease.includes('uterine') || disease.includes('uterus') || disease.includes('endometrial')) {
            val = 3.1;
        } else if (disease.includes('ovarian') || disease.includes('ovary')) {
            val = 1.3;
        }
        elements.pooledIncidence.value = val;
        updatePooledPowerAnalysis();
    }

    if (elements.disease) {
        elements.disease.addEventListener('change', updateBaselineIncidence);
        updateBaselineIncidence();
    }

    if (elements.analyzeBtn) {
        elements.analyzeBtn.addEventListener('click', () => runAnalysis(false));
    }

    if (elements.refreshBtn) {
        elements.refreshBtn.addEventListener('click', () => {
            if (confirm("Are you sure you want to force a new LLM extraction? This may take a few minutes.")) {
                runAnalysis(true);
            }
        });
    }

    // Run Analysis Function
    async function runAnalysis(forceRefresh = false) {
        const disease = elements.disease.value;
        const exposure = elements.exposure.value;
        const outcome = elements.outcome.value;
        const excludeMeta = elements.excludeMeta.checked;
        const model = elements.model ? elements.model.value : "openai.gpt-4o";

        if (!disease || !exposure) {
            alert("Please enter both disease and exposure.");
            return;
        }

        elements.loading.classList.remove('hidden');
        elements.results.classList.add('hidden');
        elements.errorMsg.classList.add('hidden');

        try {
            const response = await fetch('/analyze', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    disease,
                    exposure,
                    outcome,
                    exclude_meta: excludeMeta,
                    model: model,
                    use_downstream: useDownstream,
                    force_refresh: forceRefresh
                })
            });

            let data;
            try {
                data = await response.json();
            } catch (jsonErr) {
                // Ignore json parse error if not JSON
            }

            if (!response.ok) {
                const errMsg = (data && data.error) ? data.error : `Server returned ${response.status}: ${response.statusText}`;
                throw new Error(errMsg);
            }

            if (data && data.error) {
                elements.errorMsg.textContent = data.error;
                elements.errorMsg.classList.remove('hidden');
            } else {
                allStudies = data.studies;

                currentStudies = data.studies;
                updateResultsUI(data);
                renderStudiesTable();
                elements.results.classList.remove('hidden');

                // Auto-trigger Update Analysis so only selected studies are included
                if (elements.updateBtn) {
                    setTimeout(() => elements.updateBtn.click(), 500);
                }
            }
        } catch (e) {
            elements.errorMsg.textContent = `Error: ${e.message}. Please check your connection and server status.`;
            elements.errorMsg.classList.remove('hidden');
            console.error("Analyze error:", e);
        } finally {
            elements.loading.classList.add('hidden');
        }
    }

    // Update (Re-analyze) Logic
    if (elements.updateBtn) {
        elements.updateBtn.addEventListener('click', async () => {
            const checkboxes = document.querySelectorAll('.study-checkbox');
            const selectedStudies = [];

            checkboxes.forEach((cb) => {
                if (cb.checked) {
                    const idx = cb.getAttribute('data-index');
                    selectedStudies.push(currentStudies[idx]);
                }
            });

            if (selectedStudies.length === 0) {
                alert("Please select at least one study.");
                return;
            }

            elements.updateBtn.textContent = "Updating...";
            elements.updateBtn.disabled = true;

            try {
                const res = await fetch('/reanalyze', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        studies: selectedStudies,
                        disease: elements.disease.value,
                        exposure: elements.exposure.value,
                        outcome: elements.outcome ? elements.outcome.value : 'Incidence',
                        exclude_meta: elements.excludeMeta ? elements.excludeMeta.checked : false
                    })
                });

                const data = await res.json();
                if (data.error) alert(data.error);
                else updateResultsUI(data);
            } catch (e) {
                console.error("Update error:", e);
                alert("Failed to update analysis.");
            } finally {
                elements.updateBtn.textContent = "Update Analysis";
                elements.updateBtn.disabled = false;
            }
        });
    }

    // Render Table
    function renderStudiesTable() {
        if (!elements.studiesTbody) return;
        elements.studiesTbody.innerHTML = '';

        currentStudies.forEach((study, index) => {
            const tr = document.createElement('tr');
            const outcomeTerm = elements.outcome ? (elements.outcome.value === 'Survival' ? 'Events' : 'Cases') : 'Cases';

            if (study.verification_status === 'consensus') tr.style.backgroundColor = '#f0fff4';


            // Checkbox logic
            const rawCases = String(study['Cases'] !== undefined && study['Cases'] !== null ? study['Cases'] : '').replace(/,/g, '');
            const casesVal = parseInt(rawCases);
            
            let estCasesVal = parseInt(study['Estimated Cases']);
            if (isNaN(estCasesVal)) {
                const totalN = parseInt(String(study.Participants || study['Sample Size'] || '').replace(/,/g, ''));
                if (!isNaN(totalN)) {
                    const dScope = document.getElementById('disease') ? document.getElementById('disease').value.toLowerCase() : 'breast cancer';
                    let prev = 0.0;
                    if (dScope.includes('breast')) prev = 0.13;
                    else if (dScope.includes('ovarian') || dScope.includes('ovary')) prev = 0.013;
                    else if (dScope.includes('uterine') || dScope.includes('uterus') || dScope.includes('endometrial')) prev = 0.031;
                    
                    if (prev > 0) {
                        estCasesVal = Math.round(totalN * prev);
                        study['Estimated Cases'] = estCasesVal; // Cache it dynamically
                    }
                }
            }
            const finalCasesVal = !isNaN(casesVal) ? casesVal : (!isNaN(estCasesVal) ? estCasesVal : NaN);
            const isARR = (study['Effect Type'] || '').toUpperCase() === 'ARR';
            const minCases = elements.filterMinCases ? (parseInt(elements.filterMinCases.value) || 0) : 50;
            const isExcludedByFlag = (study.exclusions || 0) >= 2;
            const isChecked = (!isARR && !isNaN(finalCasesVal) && finalCasesVal > minCases && !isExcludedByFlag) ? 'checked' : '';

            // Build Exclusion Reason Title
            let unselectedReason = "";
            if (!isChecked) {
                if (isExcludedByFlag) unselectedReason = "Excluded: Flagged for removal by users";
                else if (isARR) unselectedReason = "Excluded: Effect type is ARR";
                else if (isNaN(finalCasesVal)) unselectedReason = "Excluded: Cases not specified or invalid";
                else if (finalCasesVal <= minCases) {
                    const isEst = isNaN(casesVal);
                    unselectedReason = `Excluded: Cases ≤ ${minCases}${isEst ? ' (estimated)' : ''}`;
                }
            }

            // Build Quality Hover Details
            let qualityDetails = study['Quality Score'] || 'Fair';
            if (study.JBI && typeof study.JBI === 'object') {
                const answers = Object.entries(study.JBI)
                    .sort(([a], [b]) => {
                        const numA = parseInt(a.replace(/[^0-9]/g, '')) || 0;
                        const numB = parseInt(b.replace(/[^0-9]/g, '')) || 0;
                        return numA - numB;
                    })
                    .map(([q, ans]) => `${q.toUpperCase()}: ${ans}`)
                    .join('\n');
                qualityDetails += `\n\nJBI Assessment:\n${answers}`;
            }

            tr.title = ""; // Removed whole-row tooltip
            if (isExcludedByFlag) {
                tr.style.opacity = '0.7';
                tr.style.backgroundColor = 'rgba(255, 0, 0, 0.08)'; // Red watermark
            } else if (!isChecked) {
                tr.style.opacity = '0.6'; // Make initially excluded rows look slightly faded
                tr.style.backgroundColor = 'rgba(200, 200, 200, 0.15)';
            }

            tr.innerHTML = `
                <td style="text-align: center; padding: 0.75rem; vertical-align: middle;">
                    <button class="expand-btn" data-index="${index}" style="background: none; border: none; color: var(--primary); padding: 0; cursor: pointer; font-size: 1.1rem; width: 100%; display: flex; align-items: center; justify-content: center; transition: transform 0.2s;" onclick="window.toggleStudyDetails(${index}, this)">▶</button>
                </td>
                <td><input type="checkbox" class="study-checkbox" data-index="${index}" ${isChecked}></td>
                <td>${index + 1}</td>
                <td title="${unselectedReason}">
                    <a href="${study.Link}" target="_blank" style="color: var(--primary); text-decoration: none; font-weight: 800;">
                        ${(() => {
                            let parts = study.Study.split(' ');
                            let first = parts[0].toLowerCase();
                            if (first === 'van' || first === 'de' || first === 'la' || first === 'al') {
                                let nameParts = [];
                                for (let p of parts) {
                                    if (p === 'et' || p.startsWith('(')) break;
                                    nameParts.push(p);
                                }
                                if (nameParts.length > 1) nameParts.pop();
                                return nameParts.join(' ') + ' et al.';
                            }
                            return parts[0] + ' et al.';
                        })()}
                    </a>
                </td>
                <td>
                    <div style="display: flex; flex-direction: column; gap: 2px;">
                        <div style="display: flex; align-items: center; gap: 2px;">
                            <span style="font-size: 0.7em; min-width: 20px;">${study['Effect Type'] || 'OR'}</span>
                            <input type="number" step="0.001" value="${parseFloat(study['Effect Size'] || 1).toFixed(3)}" 
                                   style="width: 60px; font-size: 0.8em;"
                                   onchange="currentStudies[${index}]['Effect Size'] = parseFloat(this.value)">
                        </div>
                        ${(() => {
                            const es = parseFloat(study['Effect Size']);
                            const type = (study['Effect Type'] || 'OR').toUpperCase();
                            if (!isNaN(es)) {
                                const dScope = document.getElementById('disease') ? document.getElementById('disease').value.toLowerCase() : 'breast cancer';
                                let p0 = 0.13;
                                if (dScope.includes('uterine') || dScope.includes('uterus') || dScope.includes('endometrial')) {
                                    p0 = 0.031;
                                } else if (dScope.includes('ovarian') || dScope.includes('ovary')) {
                                    p0 = 0.013;
                                }
                                const pctText = (p0 * 100).toFixed(1).replace('.0', '') + '%';
                                if (type === 'OR' || type === 'ODDS RATIO') {
                                    const rr = es / (1 - p0 + (p0 * es));
                                    return `<div style="font-size: 0.65em; color: #777; padding-left: 2px;" title="Estimated Relative Risk (assuming ${pctText} baseline risk)">Est. RR: ${rr.toFixed(3)}</div>`;
                                } else if (type === 'HR' || type === 'HAZARD RATIO') {
                                    const rr = (1 / p0) * (1 - Math.exp(es * Math.log(1 - p0)));
                                    return `<div style="font-size: 0.65em; color: #777; padding-left: 2px;" title="Estimated Relative Risk (assuming ${pctText} baseline risk)">Est. RR: ${rr.toFixed(3)}</div>`;
                                }
                            }
                            return '';
                        })()}
                    </div>
                </td>
                <td>
                    <div style="display: flex; gap: 2px;">
                        <input type="number" step="0.001" value="${parseFloat(study['Lower CI'] || 0.5).toFixed(3)}" style="width: 50px; font-size: 0.8em;" onchange="currentStudies[${index}]['Lower CI'] = parseFloat(this.value)">
                        <input type="number" step="0.001" value="${parseFloat(study['Upper CI'] || 1.5).toFixed(3)}" style="width: 50px; font-size: 0.8em;" onchange="currentStudies[${index}]['Upper CI'] = parseFloat(this.value)">
                    </div>
                </td>
                <td>
                    <div style="display:flex; flex-direction:column; gap:3px;">
                        <div style="display:flex; align-items:center; gap:3px; font-size:0.75em;">
                            <span style="opacity:0.65;">N:</span>
                            <input type="number" step="1" value="${parseInt(String(study.Participants || study['Sample Size'] || '').replace(/,/g,'')||0) || ''}"
                                   style="width:68px; font-size:0.95em;"
                                   onchange="currentStudies[${index}]['Sample Size'] = parseInt(this.value); currentStudies[${index}]['Participants'] = parseInt(this.value);">
                        </div>
                        <div style="display:flex; align-items:center; gap:3px; font-size:0.75em;">
                            <span style="opacity:0.65;">${outcomeTerm}:</span>
                            <input type="number" step="1" 
                                   value="${study.Cases !== undefined && study.Cases !== null ? parseInt(String(study.Cases).replace(/,/g,'')) : ''}"
                                   placeholder="${study['Estimated Cases'] !== undefined && study['Estimated Cases'] !== null ? 'est. ' + study['Estimated Cases'] : ''}"
                                   style="width:68px; font-size:0.95em;"
                                   onchange="(function(inp, idx){
                                        const v = parseInt(inp.value);
                                        currentStudies[idx]['Cases'] = isNaN(v) ? inp.value : v;
                                        const est = parseInt(currentStudies[idx]['Estimated Cases']);
                                        const finalVal = !isNaN(v) ? v : (!isNaN(est) ? est : NaN);
                                        const minC = document.getElementById('filter-min-cases') ? (parseInt(document.getElementById('filter-min-cases').value)||0) : 50;
                                        const cb = document.querySelector('.study-checkbox[data-index=\''+idx+'\']');
                                        const row = cb ? cb.closest('tr') : null;
                                        if(cb){
                                            const shouldCheck = !isNaN(finalVal) && finalVal > minC;
                                            cb.checked = shouldCheck;
                                            if(row){ row.style.opacity = shouldCheck ? '' : '0.6'; row.style.backgroundColor = shouldCheck ? '' : 'rgba(200,200,200,0.15)'; }
                                        }
                                    })(this, ${index})">
                        </div>
                    </div>
                </td>
                <td>
                    <div class="quality-badge quality-${(study['Quality Score'] || 'fair').toLowerCase()}" 
                         title="${qualityDetails}"
                         style="font-size: 0.7rem; padding: 2px 6px; border-radius: 12px; color: white; cursor: help;">
                         ${study['Quality Score'] || 'Fair'}
                    </div>
                </td>
                <td>
                    <button onclick="window.verifyStudy('${study.PMID}', this)" style="cursor: pointer;">✓ ${study.verifications || 0}</button>
                </td>
                <td>
                    <button onclick="window.excludeStudy('${study.PMID}', this)" 
                            style="cursor: pointer; background: ${study.exclusions > 0 ? '#ff4d4d' : '#6c757d'}; color: white; border: none; padding: 2px 8px; border-radius: 4px;"
                            title="Exclude this study (2 flags hides it)">
                        ✖ ${study.exclusions || 0}
                    </button>
                </td>
                <td style="font-size: 0.75em;" title="${unselectedReason}">${study.Reference || '-'}</td>
                <td style="font-size: 0.75em;" title="${unselectedReason}">
                    <b>Context:</b> ${study.comparison_type || '-'}<br>
                    <b>Design:</b> ${study.Design || '-'}<br>
                    <b>Location:</b> ${study.Continent || '-'}<br>
                    <b>Exposure Quant:</b>
                    <select onchange="currentStudies[${index}]['exposure_measurement_type'] = this.value; (function(selectEl) {
                        const val = selectEl.value;
                        if (val === 'dietary_intake') selectEl.style.color = '#2e7d32';
                        else if (val === 'human_biospecimen') selectEl.style.color = '#1565c0';
                        else selectEl.style.color = '#e65100';
                    })(this)" style="font-weight: bold; border: 1px solid #ccc; border-radius: 4px; padding: 2px; font-size: 0.95em; color: ${
                        (() => {
                            const t = study.exposure_measurement_type || 'unclear';
                            if (t === 'dietary_intake') return '#2e7d32';
                            if (t === 'human_biospecimen') return '#1565c0';
                            return '#e65100';
                        })()
                    }">
                        <option value="unclear" ${(!study.exposure_measurement_type || study.exposure_measurement_type === 'unclear') ? 'selected' : ''}>Unclear</option>
                        <option value="dietary_intake" ${study.exposure_measurement_type === 'dietary_intake' ? 'selected' : ''}>Dietary Intake</option>
                        <option value="human_biospecimen" ${study.exposure_measurement_type === 'human_biospecimen' ? 'selected' : ''}>Human Biospecimen</option>
                    </select>
                </td>
                <td style="font-size: 0.75em;" title="${unselectedReason}">${study.Journal || '-'} (${study.Year || '-'})</td>
            `;

            // Build Details row
            const detailsTr = document.createElement('tr');
            detailsTr.className = 'details-row hidden';
            detailsTr.id = `details-row-${index}`;
            if (study.verification_status === 'consensus') detailsTr.style.backgroundColor = '#f0fff4';
            else if (isExcludedByFlag) detailsTr.style.backgroundColor = 'rgba(255, 0, 0, 0.08)';
            else if (!isChecked) detailsTr.style.backgroundColor = 'rgba(200, 200, 200, 0.15)';
            else detailsTr.style.backgroundColor = '#fafafa';

            // Get supporting text dictionary safely
            const est = study.extraction_supporting_text || {
                "sample_size": "",
                "effect_size": "",
                "effect_direction": "",
                "p_value": "",
                "confidence_interval": "",
                "outcome_definition": "",
                "exposure_definition": ""
            };

            detailsTr.innerHTML = `
                <td colspan="13" style="padding: 1.25rem 2rem; border-bottom: 1px solid var(--border);">
                    <div class="snippets-container" style="display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 1.25rem; border-left: 4px solid var(--primary); padding-left: 1.25rem; margin-left: 0.5rem;">
                        <div class="snippet-item" style="display: flex; flex-direction: column; gap: 0.25rem;">
                            <span style="font-weight: 700; color: #555; font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.05em;">Exposure Measurement Explanation</span>
                            <span style="font-size: 0.88rem; font-style: italic; color: #111; line-height: 1.45;">${study.exposure_measurement_supporting_text ? `"${study.exposure_measurement_supporting_text}"` : '<i>Not available</i>'}</span>
                        </div>
                        <div class="snippet-item" style="display: flex; flex-direction: column; gap: 0.25rem;">
                            <span style="font-weight: 700; color: #555; font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.05em;">Sample Size Quote</span>
                            <span style="font-size: 0.88rem; font-style: italic; color: #111; line-height: 1.45;">${est.sample_size ? `"${est.sample_size}"` : '<i>Not available</i>'}</span>
                        </div>
                        <div class="snippet-item" style="display: flex; flex-direction: column; gap: 0.25rem;">
                            <span style="font-weight: 700; color: #555; font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.05em;">Effect Size Quote</span>
                            <span style="font-size: 0.88rem; font-style: italic; color: #111; line-height: 1.45;">${est.effect_size ? `"${est.effect_size}"` : '<i>Not available</i>'}</span>
                        </div>
                        <div class="snippet-item" style="display: flex; flex-direction: column; gap: 0.25rem;">
                            <span style="font-weight: 700; color: #555; font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.05em;">Effect Direction Quote</span>
                            <span style="font-size: 0.88rem; font-style: italic; color: #111; line-height: 1.45;">${est.effect_direction ? `"${est.effect_direction}"` : '<i>Not available</i>'}</span>
                        </div>
                        <div class="snippet-item" style="display: flex; flex-direction: column; gap: 0.25rem;">
                            <span style="font-weight: 700; color: #555; font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.05em;">P-Value Quote</span>
                            <span style="font-size: 0.88rem; font-style: italic; color: #111; line-height: 1.45;">${est.p_value ? `"${est.p_value}"` : '<i>Not available</i>'}</span>
                        </div>
                        <div class="snippet-item" style="display: flex; flex-direction: column; gap: 0.25rem;">
                            <span style="font-weight: 700; color: #555; font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.05em;">Confidence Interval Quote</span>
                            <span style="font-size: 0.88rem; font-style: italic; color: #111; line-height: 1.45;">${est.confidence_interval ? `"${est.confidence_interval}"` : '<i>Not available</i>'}</span>
                        </div>
                        <div class="snippet-item" style="display: flex; flex-direction: column; gap: 0.25rem;">
                            <span style="font-weight: 700; color: #555; font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.05em;">Outcome Definition Quote</span>
                            <span style="font-size: 0.88rem; font-style: italic; color: #111; line-height: 1.45;">${est.outcome_definition ? `"${est.outcome_definition}"` : '<i>Not available</i>'}</span>
                        </div>
                        <div class="snippet-item" style="display: flex; flex-direction: column; gap: 0.25rem;">
                            <span style="font-weight: 700; color: #555; font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.05em;">Exposure Definition Quote</span>
                            <span style="font-size: 0.88rem; font-style: italic; color: #111; line-height: 1.45;">${est.exposure_definition ? `"${est.exposure_definition}"` : '<i>Not available</i>'}</span>
                        </div>
                    </div>
                </td>
            `;

            elements.studiesTbody.appendChild(tr);
            elements.studiesTbody.appendChild(detailsTr);
        });
        updateSortIcons();
    }

    // Toggle details row visibility
    window.toggleStudyDetails = (index, btn) => {
        const detailsRow = document.getElementById(`details-row-${index}`);
        if (!detailsRow) return;
        
        if (detailsRow.classList.contains('hidden')) {
            detailsRow.classList.remove('hidden');
            btn.textContent = '▼';
            btn.style.color = 'var(--primary-hover)';
        } else {
            detailsRow.classList.add('hidden');
            btn.textContent = '▶';
            btn.style.color = 'var(--primary)';
        }
    };

    // Verify Study (attached to window for inline onclick)
    window.verifyStudy = async (pmid, btn) => {
        if (!pmid) return;
        const study = currentStudies.find(s => s.PMID === pmid);
        const disease = elements.disease.value;
        const exposure = elements.exposure.value;
        const outcome = elements.outcome.value;
        const context_key = `${disease}_${exposure}_${outcome}`.toLowerCase().replace(/ /g, "_");
        
        try {
            const res = await fetch('/verify', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ pmid, study_data: study, disease, exposure, outcome })
            });
            if (res.ok) {
                const data = await res.json();
                btn.textContent = `✓ ${data.count}`;
                if (data.status === 'consensus') btn.style.background = '#2ea44f';
            }
        } catch (e) {
            console.error("Verify error:", e);
        }
    };

    window.excludeStudy = async (pmid, btn) => {
        if (!pmid) return;
        if (!confirm("Flag this study for exclusion? (2 flags will hide it permanently)")) return;

        try {
            const disease = elements.disease.value;
            const exposure = elements.exposure.value;
            const outcome = elements.outcome.value;
            const context_key = `${disease}_${exposure}_${outcome}`.toLowerCase().replace(/ /g, "_");

            const res = await fetch('/exclude', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ pmid, disease, exposure, outcome })
            });
            if (res.ok) {
                const data = await res.json();
                btn.textContent = `✖ ${data.exclusions}`;
                btn.style.background = '#ff4d4d';
                if (data.exclusions >= 2) {
                    alert("Study flagged for removal. It has been automatically deselected and marked.");
                    const row = btn.closest('tr');
                    row.style.opacity = '0.7';
                    row.style.backgroundColor = 'rgba(255, 0, 0, 0.08)';
                    const cb = row.querySelector('.study-checkbox');
                    if (cb && cb.checked) {
                        cb.checked = false;
                        if (elements.updateBtn) {
                            setTimeout(() => elements.updateBtn.click(), 500);
                        }
                    }
                    row.querySelectorAll('input, button:not([onclick^="window.excludeStudy"])').forEach(el => el.disabled = true);
                }
            }
        } catch (e) {
            console.error("Exclude error:", e);
        }
    };

    // Sorting
    window.handleSort = (field) => {
        if (currentSort.field === field) currentSort.direction = currentSort.direction === 'asc' ? 'desc' : 'asc';
        else { currentSort.field = field; currentSort.direction = 'asc'; }

        currentStudies.sort((a, b) => {
            let valA = a[field], valB = b[field];
            if (field === 'Effect Size') { valA = parseFloat(a[field]); valB = parseFloat(b[field]); }
            if (valA < valB) return currentSort.direction === 'asc' ? -1 : 1;
            if (valA > valB) return currentSort.direction === 'asc' ? 1 : -1;
            return 0;
        });
        renderStudiesTable();
    };

    function updateSortIcons() {
        document.querySelectorAll('th.sortable').forEach(th => th.classList.remove('sort-asc', 'sort-desc'));
        const map = { 'Study': 'th-study', 'Effect Size': 'th-es', 'Year': 'th-year' };
        const id = map[currentSort.field];
        if (id) {
            const el = document.getElementById(id);
            if (el) el.classList.add(currentSort.direction === 'asc' ? 'sort-asc' : 'sort-desc');
        }
    }

    function updateLastUpdated(ts = null) {
        if (!elements.lastUpdated) return;
        const date = ts ? new Date(ts) : new Date();
        elements.lastUpdated.textContent = date.toLocaleString();
    }
    function updateResultsUI(data) {
        if (elements.forestPlot) elements.forestPlot.src = `/${data.plot_url}?t=${Date.now()}`;
        if (elements.funnelPlot && data.funnel_plot_url) elements.funnelPlot.src = `/${data.funnel_plot_url}?t=${Date.now()}`;

        if (data.headline && elements.headlineResult) {
            elements.headlineResult.classList.remove('hidden');
            elements.pooledEs.textContent = data.headline.pooled_es;
            elements.pooledCi.textContent = `${data.headline.ci_low}, ${data.headline.ci_upp}`;
            elements.interpretation.textContent = data.headline.interpretation;

            // Estimated RR
            const dScope = document.getElementById('disease') ? document.getElementById('disease').value.toLowerCase() : 'breast cancer';
            let p0 = 0.13;
            if (dScope.includes('uterine') || dScope.includes('uterus') || dScope.includes('endometrial')) {
                p0 = 0.031;
            } else if (dScope.includes('ovarian') || dScope.includes('ovary')) {
                p0 = 0.013;
            }
            const es = parseFloat(data.headline.pooled_es);
            const ciLow = parseFloat(data.headline.ci_low);
            const ciUpp = parseFloat(data.headline.ci_upp);
            // Since the pooled result is now explicitly calculated as an RR in the backend,
            // we no longer need to show the estimated OR/HR conversions for the headline.
            const rrContainer = document.getElementById('estimated-rr-container');
            if (rrContainer) {
                rrContainer.style.display = 'none';
            }

            // Save original data for measure transformation toggle
            lastHeadlineData = JSON.parse(JSON.stringify(data.headline));
            if (elements.displayMeasure) {
                // Reset to RR whenever new data is loaded
                elements.displayMeasure.value = 'RR';
            }
            applyResultMeasureTransformation();

            // Heterogeneity & Egger's
            if (elements.heterogeneityStats) {
                elements.heterogeneityStats.classList.remove('hidden');
                elements.valI2.textContent = data.headline.i2 !== null ? data.headline.i2 : '-';
                elements.valTau2.textContent = data.headline.tau2 !== null ? data.headline.tau2 : '-';
                elements.valEggers.textContent = (data.headline.eggers_p !== null && data.headline.eggers_p !== undefined) ? data.headline.eggers_p.toFixed(4) : '-';
            }

            // Funnel Interpretation
            if (elements.funnelInterpretation) {
                elements.funnelInterpretation.textContent = data.headline.funnel_interpretation || 'No interpretation available.';
            }

            // Results Interpretation (LLM-generated)
            if (elements.resultsInterpretation) {
                elements.resultsInterpretation.textContent = data.headline.results_interpretation || '';
                elements.resultsInterpretation.style.display = data.headline.results_interpretation ? 'block' : 'none';
            }

            // Pooled Power Analysis Update
            updatePooledPowerAnalysis();
            if (elements.pooledIncidence && !elements.pooledIncidence.hasListener) {
                elements.pooledIncidence.addEventListener('input', updatePooledPowerAnalysis);
                elements.pooledIncidence.hasListener = true;
            }
            if (elements.powerAlpha && !elements.powerAlpha.hasListener) {
                elements.powerAlpha.addEventListener('input', updatePooledPowerAnalysis);
                elements.powerAlpha.hasListener = true;
            }
            if (elements.powerValue && !elements.powerValue.hasListener) {
                elements.powerValue.addEventListener('input', updatePooledPowerAnalysis);
                elements.powerValue.hasListener = true;
            }
            if (elements.powerSides && !elements.powerSides.hasListener) {
                elements.powerSides.addEventListener('change', updatePooledPowerAnalysis);
                elements.powerSides.hasListener = true;
            }
            if (elements.powerEffect && !elements.powerEffect.hasListener) {
                elements.powerEffect.addEventListener('change', updatePooledPowerAnalysis);
                elements.powerEffect.hasListener = true;
            }
            if (elements.powerArms && !elements.powerArms.hasListener) {
                elements.powerArms.addEventListener('change', updatePooledPowerAnalysis);
                elements.powerArms.hasListener = true;
            }

            // Influence & Sensitivity
            if (elements.influenceSection) {
                if (data.baujat_plot_url || (data.headline.loo_results && data.headline.loo_results.length > 0)) {
                    elements.influenceSection.classList.remove('hidden');
                    if (elements.baujatPlot && data.baujat_plot_url) {
                        elements.baujatPlot.src = `/${data.baujat_plot_url}?t=${Date.now()}`;
                    }
                    if (elements.looTbody && data.headline.loo_results) {
                        elements.looTbody.innerHTML = '';
                        data.headline.loo_results.forEach(res => {
                            const tr = document.createElement('tr');
                            tr.innerHTML = `
                                <td>${res.omitted}</td>
                                <td style="color: ${res.is_significant ? '#A0522D' : '#666'}">
                                    ${(res.pooled_es !== undefined && res.pooled_es !== null) ? res.pooled_es.toFixed(2) : '-'} (${(res.ci_low !== undefined && res.ci_low !== null) ? res.ci_low.toFixed(2) : '-'}, ${(res.ci_upp !== undefined && res.ci_upp !== null) ? res.ci_upp.toFixed(2) : '-'})
                                </td>
                            `;
                            elements.looTbody.appendChild(tr);
                        });
                    }
                } else {
                    elements.influenceSection.classList.add('hidden');
                }
            }
        }
        updateLastUpdated(data.last_run);


        // Update Table Head
        const thCases = document.getElementById('th-n-cases');
        if (thCases && elements.outcome) {
            const term = elements.outcome.value === 'Survival' ? 'Events' : 'Cases';
            thCases.textContent = `N / ${term}`;
        }
    }

    // Measure Transformation Logic
    if (elements.displayMeasure) {
        elements.displayMeasure.addEventListener('change', applyResultMeasureTransformation);
    }

    function applyResultMeasureTransformation() {
        if (!lastHeadlineData || !elements.pooledEs || !elements.pooledCi) return;

        const measure = elements.displayMeasure ? elements.displayMeasure.value : 'RR';
        const dScope = document.getElementById('disease') ? document.getElementById('disease').value.toLowerCase() : 'breast cancer';
        let p0 = 0.13;
        if (dScope.includes('uterine') || dScope.includes('uterus') || dScope.includes('endometrial')) {
            p0 = 0.031;
        } else if (dScope.includes('ovarian') || dScope.includes('ovary')) {
            p0 = 0.013;
        }
        let es = parseFloat(lastHeadlineData.pooled_es);
        let low = parseFloat(lastHeadlineData.ci_low);
        let upp = parseFloat(lastHeadlineData.ci_upp);
        let pi_low = lastHeadlineData.pi_low !== undefined && lastHeadlineData.pi_low !== null ? parseFloat(lastHeadlineData.pi_low) : null;
        let pi_upp = lastHeadlineData.pi_upp !== undefined && lastHeadlineData.pi_upp !== null ? parseFloat(lastHeadlineData.pi_upp) : null;

        let label = "Pooled Relative Risk (RR)";

        if (measure === 'OR') {
            label = "Pooled Odds Ratio (OR)";
            es = (es * (1 - p0)) / (1 - es * p0);
            low = (low * (1 - p0)) / (1 - low * p0);
            upp = (upp * (1 - p0)) / (1 - upp * p0);
            if (pi_low !== null) pi_low = (pi_low * (1 - p0)) / (1 - pi_low * p0);
            if (pi_upp !== null) pi_upp = (pi_upp * (1 - p0)) / (1 - pi_upp * p0);
        } else if (measure === 'HR') {
            label = "Pooled Hazard Ratio (HR)";
            es = Math.log(1 - p0 * es) / Math.log(1 - p0);
            low = Math.log(1 - p0 * low) / Math.log(1 - p0);
            upp = Math.log(1 - p0 * upp) / Math.log(1 - p0);
            if (pi_low !== null) pi_low = Math.log(1 - p0 * pi_low) / Math.log(1 - p0);
            if (pi_upp !== null) pi_upp = Math.log(1 - p0 * pi_upp) / Math.log(1 - p0);
        }

        // Update UI
        if (elements.pooledLabel) elements.pooledLabel.textContent = label;
        elements.pooledEs.textContent = isNaN(es) ? 'N/A' : es.toFixed(2);
        elements.pooledCi.textContent = `${isNaN(low) ? 'N/A' : low.toFixed(2)}, ${isNaN(upp) ? 'N/A' : upp.toFixed(2)}`;
        if (elements.piContainer && elements.pooledPi) {
            if (pi_low !== null && pi_upp !== null && !isNaN(pi_low) && !isNaN(pi_upp)) {
                elements.pooledPi.textContent = `${pi_low.toFixed(2)}, ${pi_upp.toFixed(2)}`;
                elements.piContainer.style.display = 'inline';
            } else {
                elements.piContainer.style.display = 'none';
            }
        }

        // Update Headline Interpretation text (e.g. increased risk/odds)
        if (elements.interpretation && lastHeadlineData.interpretation) {
            let interp = lastHeadlineData.interpretation;
            if (measure === 'OR') {
                interp = interp.replace(/risk\/odds/g, 'odds').replace(/\brisk\b/g, 'odds');
            } else if (measure === 'HR') {
                interp = interp.replace(/risk\/odds/g, 'hazard').replace(/\brisk\b/g, 'hazard');
            } else {
                interp = interp.replace(/risk\/odds/g, 'risk').replace(/\bodds\b/g, 'risk').replace(/\bhazard\b/g, 'risk');
            }
            // Ensure CI is capitalized
            interp = interp.replace(/\bci\b/gi, 'CI');
            elements.interpretation.textContent = interp;
        }

        // Also update interpretation text if it contains the old numbers
        if (elements.resultsInterpretation && lastHeadlineData.results_interpretation) {
            let text = lastHeadlineData.results_interpretation;
            const oldES = lastHeadlineData.pooled_es.toFixed(2);
            const oldLow = lastHeadlineData.ci_low.toFixed(2);
            const oldUpp = lastHeadlineData.ci_upp.toFixed(2);

            const newES = isNaN(es) ? 'N/A' : es.toFixed(2);
            const newLow = isNaN(low) ? 'N/A' : low.toFixed(2);
            const newUpp = isNaN(upp) ? 'N/A' : upp.toFixed(2);

            // Replace values in the interpretation text
            text = text.replace(new RegExp(oldES, 'g'), newES);
            text = text.replace(new RegExp(oldLow, 'g'), newLow);
            text = text.replace(new RegExp(oldUpp, 'g'), newUpp);
            
            // Replace word "risk" with "odds"/"hazard"
            if (measure === 'OR') {
                text = text.replace(/\brisk\b/gi, 'odds');
            } else if (measure === 'HR') {
                text = text.replace(/\brisk\b/gi, 'hazard');
            }

            // Ensure CI is capitalized
            text = text.replace(/\bci\b/gi, 'CI');
            
            elements.resultsInterpretation.textContent = text;
        }

        // Keep pooled power analysis in sync
        updatePooledPowerAnalysis();
    }

    function updatePooledPowerAnalysis() {
        if (!lastHeadlineData || !elements.pooledPowerAnalysis) return;
        
        const p1 = parseFloat(elements.pooledIncidence.value) / 100.0;
        
        // Determine primaryRR based on user selection
        const effectSelection = elements.powerEffect ? elements.powerEffect.value : 'pooled';
        let primaryRR;
        let effectSelectionText = "";
        if (effectSelection === 'lower') {
            primaryRR = parseFloat(lastHeadlineData.ci_low);
            effectSelectionText = " (Lower 95% CI)";
        } else if (effectSelection === 'upper') {
            primaryRR = parseFloat(lastHeadlineData.ci_upp);
            effectSelectionText = " (Upper 95% CI)";
        } else if (effectSelection === 'pi_lower') {
            primaryRR = parseFloat(lastHeadlineData.pi_low);
            effectSelectionText = " (Lower 95% PI)";
        } else if (effectSelection === 'pi_upper') {
            primaryRR = parseFloat(lastHeadlineData.pi_upp);
            effectSelectionText = " (Upper 95% PI)";
        } else {
            primaryRR = parseFloat(lastHeadlineData.pooled_es);
        }
        
        if ((effectSelection === 'pi_lower' && lastHeadlineData.pi_low == null) || 
            (effectSelection === 'pi_upper' && lastHeadlineData.pi_upp == null)) {
            elements.pooledPowerAnalysis.classList.remove('hidden');
            if (elements.pooledPowerEsText) elements.pooledPowerEsText.textContent = "N/A" + effectSelectionText;
            if (elements.pooledPowerNTotal) elements.pooledPowerNTotal.textContent = "N/A (≥3 studies required)";
            if (elements.pooledPowerPerGroup) elements.pooledPowerPerGroup.textContent = "";
            if (elements.pooledPowerCases) elements.pooledPowerCases.textContent = "-";
            return;
        }

        if (isNaN(primaryRR) || isNaN(p1) || p1 <= 0 || p1 >= 1) {
            elements.pooledPowerAnalysis.classList.add('hidden');
            return;
        }

        elements.pooledPowerAnalysis.classList.remove('hidden');
        if (elements.pooledPowerEsText) elements.pooledPowerEsText.textContent = primaryRR.toFixed(2) + effectSelectionText;

        // Alpha, Power, Sides
        const alpha = elements.powerAlpha ? parseFloat(elements.powerAlpha.value) : 0.05;
        const power = elements.powerValue ? parseFloat(elements.powerValue.value) : 0.80;
        const sides = elements.powerSides ? parseInt(elements.powerSides.value) : 2;
        
        if (elements.alphaTextDisplay) elements.alphaTextDisplay.textContent = alpha;
        if (elements.powerTextDisplay) elements.powerTextDisplay.textContent = `${(power * 100).toFixed(0)}% power`;
        if (elements.sidesTextDisplay) elements.sidesTextDisplay.textContent = sides === 1 ? 'one-sided' : 'two-sided';
        
        const p2 = p1 * primaryRR;
        const zAlpha = getZ(1 - alpha / sides);
        const zBeta = getZ(power);
        const pBar = (p1 + p2) / 2.0;
        const qBar = 1.0 - pBar;
        const diff = p1 - p2;

        if (Math.abs(diff) < 1e-8) {
            elements.pooledPowerNTotal.textContent = "N/A (RR=1.0)";
            if (elements.pooledPowerPerGroup) elements.pooledPowerPerGroup.textContent = "";
            elements.pooledPowerCases.textContent = "-";
            return;
        }

        const arms = elements.powerArms ? parseInt(elements.powerArms.value) : 2;
        let total_n, expected_cases, per_group_text = "";
        
        if (arms === 2) {
            const n_per_group = Math.pow(zAlpha * Math.sqrt(2 * pBar * qBar) + zBeta * Math.sqrt(p1 * (1 - p1) + p2 * (1 - p2)), 2) / Math.pow(diff, 2);
            total_n = Math.ceil(n_per_group) * 2;
            expected_cases = Math.ceil(total_n * pBar);
            per_group_text = `(${Math.ceil(n_per_group).toLocaleString()} per group)`;
        } else {
            // Single arm formula
            const n_single = Math.pow(zAlpha * Math.sqrt(p1 * (1 - p1)) + zBeta * Math.sqrt(p2 * (1 - p2)), 2) / Math.pow(diff, 2);
            total_n = Math.ceil(n_single);
            expected_cases = Math.ceil(total_n * p2);
            per_group_text = `(single arm)`;
        }

        if (elements.pooledPowerNTotal) elements.pooledPowerNTotal.textContent = total_n.toLocaleString();
        if (elements.pooledPowerPerGroup) elements.pooledPowerPerGroup.textContent = per_group_text;
        if (elements.pooledPowerCases) elements.pooledPowerCases.textContent = expected_cases.toLocaleString();
    }

    // --- Tab Switching Logic (Removed as only one tab remains) ---

    // --- Power Calculator Logic (Helper for integrated results calculator) ---
    function getZ(p) {
        if (p < 0.5) return -getZ(1 - p);
        const t = Math.sqrt(-2.0 * Math.log(1.0 - p));
        const c0 = 2.515517, c1 = 0.802853, c2 = 0.010328;
        const d1 = 1.432788, d2 = 0.189269, d3 = 0.001308;
        return t - (c0 + c1 * t + c2 * t * t) / (1.0 + d1 * t + d2 * t * t + d3 * t * t * t);
    }
});
