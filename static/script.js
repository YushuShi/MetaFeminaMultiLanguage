
let currentStudies = [];
let allStudies = []; // Store full dataset
let currentSort = { field: 'Quality Score', direction: 'asc' };
let useDownstream = false;
let lastHeadlineData = null; // Store original RR results for transformation
let lastHeadlineStudyCount = null;
let lastAnalysisContext = null;

function uiText(source, variables = {}) {
    if (window.MetaFeminaI18n) return window.MetaFeminaI18n.t(source, variables);
    return String(source).replace(/\{([a-zA-Z0-9_]+)\}/g, (match, key) => (
        Object.prototype.hasOwnProperty.call(variables, key) ? String(variables[key]) : match
    ));
}

// Global Error Handler for Debugging
window.onerror = function (msg, url, line, col, error) {
    console.error("Global Error:", msg, "at", url, ":", line);
    const errorMsg = document.getElementById('error-message');
    if (errorMsg) {
        errorMsg.textContent = uiText('JavaScript Error: {message} (at line {line})', { message: msg, line });
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
        model: document.getElementById('model'),
        analyzeBtn: document.getElementById('analyze-btn'),
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
        exportStudiesBtn: document.getElementById('export-studies-btn'),
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

    function meetsDefaultJbiThreshold(study) {
        const rating = String(study['Quality Score'] || '').trim().toLowerCase();
        return rating === 'good' || rating === 'moderate';
    }

    function canonicalEffectMeasure(value) {
        const effectType = String(value || '')
            .toUpperCase()
            .replace(/[^A-Z]+/g, ' ')
            .trim();
        const aliases = {
            'RISK RATIO': 'RR',
            'RELATIVE RISK': 'RR',
            'INCIDENCE RATE RATIO': 'IRR',
            'ODDS RATIO': 'OR',
            'HAZARD RATIO': 'HR'
        };
        return aliases[effectType] || effectType;
    }

    function hasEligibleEffectMeasurement(study) {
        const eligibleType = ['RR', 'IRR', 'OR', 'HR']
            .includes(canonicalEffectMeasure(study['Effect Type']));
        const effect = Number(study['Effect Size']);
        const lower = Number(study['Lower CI']);
        const upper = Number(study['Upper CI']);
        return eligibleType && effect > 0 && lower > 0 && upper > 0 && lower <= effect && effect <= upper;
    }

    function itemizedJbiEntries(study) {
        if (!study.JBI || typeof study.JBI !== 'object' || Array.isArray(study.JBI)) return [];
        return Object.entries(study.JBI)
            .filter(([question]) => /^q\d+$/i.test(question))
            .sort(([a], [b]) => {
                const numberA = parseInt(a.replace(/[^0-9]/g, '')) || 0;
                const numberB = parseInt(b.replace(/[^0-9]/g, '')) || 0;
                return numberA - numberB;
            })
            .map(([question, answer]) => ({
                question: question.toUpperCase(),
                answer: String(answer || 'Unclear')
            }));
    }

    const jbiTooltip = document.createElement('div');
    jbiTooltip.className = 'jbi-tooltip';
    jbiTooltip.id = 'jbi-item-tooltip';
    jbiTooltip.setAttribute('role', 'tooltip');
    jbiTooltip.hidden = true;
    document.body.appendChild(jbiTooltip);

    function hideJbiTooltip() {
        jbiTooltip.hidden = true;
        jbiTooltip.replaceChildren();
    }

    function showJbiTooltip(anchor, qualityScore, entries) {
        jbiTooltip.replaceChildren();

        const heading = document.createElement('div');
        heading.className = 'jbi-tooltip-heading';
        heading.textContent = uiText('JBI Assessment:');
        jbiTooltip.appendChild(heading);

        const rating = document.createElement('div');
        rating.className = 'jbi-tooltip-rating';
        rating.textContent = uiText('Overall rating: {rating}', { rating: uiText(qualityScore) });
        jbiTooltip.appendChild(rating);

        if (entries.length) {
            const list = document.createElement('dl');
            list.className = 'jbi-tooltip-list';
            entries.forEach((entry) => {
                const question = document.createElement('dt');
                question.textContent = entry.question;
                const answer = document.createElement('dd');
                answer.textContent = uiText(entry.answer);
                list.append(question, answer);
            });
            jbiTooltip.appendChild(list);
        } else {
            const unavailable = document.createElement('div');
            unavailable.className = 'jbi-tooltip-unavailable';
            unavailable.textContent = uiText('Itemized JBI assessment is unavailable.');
            jbiTooltip.appendChild(unavailable);
        }

        jbiTooltip.hidden = false;
        jbiTooltip.style.visibility = 'hidden';
        const anchorRect = anchor.getBoundingClientRect();
        const tooltipRect = jbiTooltip.getBoundingClientRect();
        const margin = 8;
        const left = Math.min(
            window.innerWidth - tooltipRect.width - margin,
            Math.max(margin, anchorRect.left + (anchorRect.width - tooltipRect.width) / 2)
        );
        let top = anchorRect.bottom + margin;
        if (top + tooltipRect.height > window.innerHeight - margin) {
            top = Math.max(margin, anchorRect.top - tooltipRect.height - margin);
        }
        jbiTooltip.style.left = `${left}px`;
        jbiTooltip.style.top = `${top}px`;
        jbiTooltip.style.visibility = 'visible';
    }
    let exposures = [];

    function selectedExposureValue() {
        if (!elements.exposure) return '';
        const stored = elements.exposure.dataset.canonicalExposure;
        if (stored) return stored;
        const visibleValue = elements.exposure.value.trim();
        const resolved = exposures.find((exposure) => (
            exposure.toLowerCase() === visibleValue.toLowerCase()
            || uiText(exposure).toLowerCase() === visibleValue.toLowerCase()
        ));
        return resolved || visibleValue;
    }

    function setSelectedExposure(canonicalExposure) {
        if (!elements.exposure) return;
        const canonical = String(canonicalExposure || '').trim();
        if (!canonical) {
            delete elements.exposure.dataset.canonicalExposure;
            elements.exposure.value = '';
            return;
        }
        elements.exposure.dataset.canonicalExposure = canonical;
        elements.exposure.value = uiText(canonical);
    }

    function localizedAnalysisLabel(value) {
        const raw = String(value || '').trim();
        if (!raw) return raw;
        const normalized = raw.replace(/_/g, ' ').replace(/\s+/g, ' ').trim();
        const exposureMatch = exposures.find((exposure) => (
            exposure.toLowerCase() === normalized.toLowerCase()
        ));
        if (exposureMatch) return uiText(exposureMatch);

        const candidates = [raw, normalized];
        if (normalized) {
            candidates.push(normalized.charAt(0).toUpperCase() + normalized.slice(1).toLowerCase());
        }
        for (const candidate of candidates) {
            const translated = uiText(candidate);
            if (translated !== candidate) return translated;
        }
        return normalized;
    }

    function headlineDirection(measure, increased) {
        if (measure === 'OR') return uiText(increased ? 'increased odds' : 'decreased odds');
        if (measure === 'HR') return uiText(increased ? 'increased hazard' : 'decreased hazard');
        return uiText(increased ? 'increased risk' : 'decreased risk');
    }

    function resultsDirection(measure, increased) {
        if (measure === 'OR') return uiText(increased ? 'higher odds' : 'lower odds');
        if (measure === 'HR') return uiText(increased ? 'higher hazard' : 'lower hazard');
        return uiText(increased ? 'higher risk' : 'lower risk');
    }

    function heterogeneityInterpretation(i2, includeBetweenStudy) {
        let level;
        let implication;
        if (i2 < 25) {
            level = includeBetweenStudy ? 'low between-study heterogeneity' : 'low heterogeneity';
            implication = 'indicating consistent findings across the included studies';
        } else if (i2 < 50) {
            level = includeBetweenStudy ? 'moderate between-study heterogeneity' : 'moderate heterogeneity';
            implication = 'suggesting some variability in the results across studies';
        } else if (i2 < 75) {
            level = includeBetweenStudy ? 'substantial between-study heterogeneity' : 'substantial heterogeneity';
            implication = 'reflecting considerable variability across studies';
        } else {
            level = includeBetweenStudy ? 'very high between-study heterogeneity' : 'very high heterogeneity';
            implication = 'reflecting highly inconsistent results across studies';
        }
        return { level: uiText(level), implication: uiText(implication) };
    }

    function renderHeadlineInterpretation(measure, es, low, upp) {
        if (!elements.interpretation || !lastHeadlineData || !lastHeadlineData.interpretation) return;
        elements.interpretation.classList.remove('notranslate');
        elements.interpretation.removeAttribute('translate');

        const original = String(lastHeadlineData.interpretation);
        const subtypeMatch = original.match(
            /^The pooled subtype-specific estimate is ([^,]+), indicating a (lower|higher) relative association for this exposure\.$/i
        );
        if (subtypeMatch) {
            elements.interpretation.textContent = uiText(
                'The pooled subtype-specific estimate is {estimate}, indicating a {direction} relative association for this exposure.',
                {
                    estimate: Number.isFinite(es) ? es.toFixed(2) : subtypeMatch[1],
                    direction: uiText(es < 1 ? 'lower' : 'higher')
                }
            );
            return;
        }

        if (/statistically significant/i.test(original)) {
            // The server determines significance from the unrounded estimate.
            // Preserve that decision instead of recalculating it from the
            // two-decimal CI displayed in the browser.
            const isSignificant = !/not statistically significant/i.test(original);
            if (!isSignificant) {
                elements.interpretation.textContent = uiText('Not statistically significant');
                return;
            }
            const increased = /increased/i.test(original) || (!/decreased/i.test(original) && es > 1);
            elements.interpretation.textContent = uiText('Statistically significant ({direction})', {
                direction: headlineDirection(measure, increased)
            });
            return;
        }

        elements.interpretation.textContent = uiText(original);
    }

    function renderResultsInterpretation(measure, es, low, upp) {
        if (!elements.resultsInterpretation || !lastHeadlineData) return;
        elements.resultsInterpretation.classList.remove('notranslate');
        elements.resultsInterpretation.removeAttribute('translate');

        const original = String(lastHeadlineData.results_interpretation || '');
        elements.resultsInterpretation.style.display = original ? 'block' : 'none';
        if (!original) {
            elements.resultsInterpretation.textContent = '';
            return;
        }

        const subtypeMatch = original.match(
            /^This saved analysis contains (\d+) separately reported (.+) (estimate|estimates)\.$/i
        );
        if (subtypeMatch) {
            const count = subtypeMatch[1];
            const template = subtypeMatch[3].toLowerCase() === 'estimate'
                ? 'This saved analysis contains {count} separately reported {category} estimate.'
                : 'This saved analysis contains {count} separately reported {category} estimates.';
            elements.resultsInterpretation.textContent = uiText(template, {
                count,
                category: localizedAnalysisLabel(subtypeMatch[2])
            });
            return;
        }

        if (!/^The pooled analysis of \d+ studies yielded/i.test(original)) {
            elements.resultsInterpretation.textContent = uiText(original);
            return;
        }

        const i2 = Number(lastHeadlineData.i2);
        if (![es, low, upp, i2].every(Number.isFinite)) {
            elements.resultsInterpretation.textContent = uiText(original);
            return;
        }

        const countMatch = original.match(/^The pooled analysis of (\d+) studies/i);
        const count = countMatch ? countMatch[1] : String(lastHeadlineStudyCount || '');
        // The saved interpretation reflects the server's unrounded test;
        // displayed CI limits may round to exactly 1.00.
        const isSignificant = !/indicating no statistically significant association/i.test(original);
        const increased = es > 1;
        // Keep the labels tied to the analysis response. A user may edit the
        // controls before changing language or effect measure.
        const exposure = localizedAnalysisLabel(
            lastAnalysisContext ? lastAnalysisContext.exposure : selectedExposureValue()
        );
        const disease = localizedAnalysisLabel(
            lastAnalysisContext ? lastAnalysisContext.disease : selectedDiseaseValue()
        );
        const common = {
            count,
            estimate: es.toFixed(2),
            low: low.toFixed(2),
            high: upp.toFixed(2),
            exposure,
            disease,
            i2: i2.toFixed(2)
        };

        if (isSignificant) {
            const heterogeneity = heterogeneityInterpretation(i2, true);
            common.direction = resultsDirection(measure, increased);
            common.heterogeneity = heterogeneity.level;
            common.implication = heterogeneity.implication;
            const template = i2 >= 50
                ? 'The pooled analysis of {count} studies yielded an overall effect size of {estimate} (95% CI: {low}–{high}), suggesting that {exposure} is associated with a {direction} of {disease}. However, this association should be interpreted with caution, as there was {heterogeneity} (I² = {i2}%), {implication}.'
                : 'The pooled analysis of {count} studies yielded an overall effect size of {estimate} (95% CI: {low}–{high}), suggesting that {exposure} is associated with a {direction} of {disease}. These findings were supported by {heterogeneity} (I² = {i2}%), {implication}.';
            elements.resultsInterpretation.textContent = uiText(template, common);
            return;
        }

        const heterogeneity = heterogeneityInterpretation(i2, false);
        common.relationship = uiText(increased ? 'positive' : 'inverse');
        common.heterogeneity = heterogeneity.level;
        common.implication = heterogeneity.implication;
        elements.resultsInterpretation.textContent = uiText(
            'The pooled analysis of {count} studies yielded an effect size of {estimate} (95% CI: {low}–{high}), indicating no statistically significant association between {exposure} and {disease}. Although the point estimate suggests a potential {relationship} relationship, the confidence interval includes the null. These findings were accompanied by {heterogeneity} (I² = {i2}%), {implication}.',
            common
        );
    }

    function renderFunnelInterpretation() {
        if (!elements.funnelInterpretation || !lastHeadlineData) return;
        elements.funnelInterpretation.classList.remove('notranslate');
        elements.funnelInterpretation.removeAttribute('translate');
        const original = String(lastHeadlineData.funnel_interpretation || '');
        if (!original) {
            elements.funnelInterpretation.textContent = uiText('No interpretation available.');
            return;
        }

        let match = original.match(
            /^Egger's test indicates no significant funnel plot asymmetry \(p=([^)]*)\)\. The distribution of studies appears symmetric, suggesting a lower risk of publication bias\.$/i
        );
        if (match) {
            elements.funnelInterpretation.textContent = uiText(
                "Egger's test indicates no significant funnel plot asymmetry (p={p}). The distribution of studies appears symmetric, suggesting a lower risk of publication bias.",
                { p: match[1] }
            );
            return;
        }

        match = original.match(
            /^The significant funnel plot asymmetry \(Egger's p=([^)]*)\) indicates substantial publication bias in this meta-analysis on (.+) and (.+)\. This specific pattern suggests that smaller studies with smaller or null effects may be underrepresented, compromising the reliability of the pooled estimate and potentially leading to an overestimation of the true association\.$/i
        );
        if (match) {
            elements.funnelInterpretation.textContent = uiText(
                "The significant funnel plot asymmetry (Egger's p={p}) indicates substantial publication bias in this meta-analysis on {exposure} and {disease}. This specific pattern suggests that smaller studies with smaller or null effects may be underrepresented, compromising the reliability of the pooled estimate and potentially leading to an overestimation of the true association.",
                {
                    p: match[1],
                    exposure: localizedAnalysisLabel(match[2]),
                    disease: localizedAnalysisLabel(match[3])
                }
            );
            return;
        }

        match = original.match(/^Egger's test p-value: (.+)\.$/i);
        if (match) {
            elements.funnelInterpretation.textContent = uiText("Egger's test p-value: {p}.", { p: match[1] });
            return;
        }

        match = original.match(/^Formal Egger's testing requires at least (\d+) eligible studies\.$/i);
        if (match) {
            elements.funnelInterpretation.textContent = uiText(
                "Formal Egger's testing requires at least {count} eligible studies.",
                { count: match[1] }
            );
            return;
        }

        match = original.match(/^Egger’s test is generally not recommended when fewer than (\d+) studies are available\.$/i);
        if (match) {
            elements.funnelInterpretation.textContent = uiText(
                'Egger’s test is generally not recommended when fewer than {count} studies are available.',
                { count: match[1] }
            );
            return;
        }

        if (/^Insufficient studies to perform formal publication bias testing\.$/i.test(original)) {
            elements.funnelInterpretation.textContent = uiText(
                'Insufficient studies to perform formal publication bias testing.'
            );
            return;
        }

        if (/^Egger's test could not be estimated from the available studies\.$/i.test(original)) {
            elements.funnelInterpretation.textContent = uiText(
                "Egger's test could not be estimated from the available studies."
            );
            return;
        }

        if (/^No interpretation available\.$/i.test(original)) {
            elements.funnelInterpretation.textContent = uiText('No interpretation available.');
            return;
        }

        elements.funnelInterpretation.textContent = uiText(original);
    }

    window.addEventListener('metafemina:languagechange', () => {
        if (!elements.exposure) return;
        const canonical = elements.exposure.dataset.canonicalExposure;
        if (canonical) setSelectedExposure(canonical);
        if (elements.exposureOptions && elements.exposureOptions.style.display === 'block') {
            elements.exposure.dispatchEvent(new Event('input'));
        }
    });

    // Verify critical elements
    for (const [name, el] of Object.entries(elements)) {
        if (!el && !['stageFilterContainer', 'funnelPlot'].includes(name)) {
            console.warn(`Critical element missing: ${name}`);
        }
    }

    // Initialize Last Updated - removed default call to avoid showing current time on load

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
        setSelectedExposure('Vitamin A'); // Default as requested

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
                if (configData.last_updated) {
                    updateLastUpdated(configData.last_updated);
                }
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

            // Show Read-Only banner
            const banner = document.getElementById('read-only-banner');
            if (banner) banner.classList.remove('hidden');


        }

        // Show synonyms for current exposure value on load
        updateSynonymsBox(selectedExposureValue());

        // Toggle listener
        const downstreamToggle = document.getElementById('use-downstream-toggle');
        if (downstreamToggle) {
            downstreamToggle.addEventListener('change', () => {
                useDownstream = downstreamToggle.checked;
                updateSynonymsBox(selectedExposureValue());
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
                if (exp.toLowerCase().includes(lc) || uiText(exp).toLowerCase().includes(lc)) {
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
            const stored = elements.exposure.dataset.canonicalExposure;
            if (stored && val.trim().toLowerCase() !== stored.toLowerCase()
                && val.trim().toLowerCase() !== uiText(stored).toLowerCase()) {
                delete elements.exposure.dataset.canonicalExposure;
            }
            updateSynonymsBox(selectedExposureValue());
            const matches = getDropdownMatches(val.toLowerCase ? val : val);

            if (elements.exposureOptions) {
                elements.exposureOptions.innerHTML = '';
                if (matches.length > 0) {
                    matches.forEach(match => {
                        const div = document.createElement('div');
                        if (match.hint) {
                            div.innerHTML = `${uiText(match.label)} <span style="font-size:0.8em; opacity:0.65; font-style:italic;">— ${match.hint}</span>`;
                        } else {
                            div.textContent = uiText(match.label);
                        }
                        div.addEventListener('click', () => {
                            setSelectedExposure(match.value);
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

    function firstStudyValue(study, keys) {
        for (const key of keys) {
            const value = study[key];
            if (value !== undefined && value !== null && String(value).trim()) {
                return String(value).trim();
            }
        }
        return '';
    }

    function studyIdentifier(study, type) {
        const isPmcid = type === 'PMCID';
        const direct = firstStudyValue(study, isPmcid
            ? ['PMCID', 'pmcid', 'PMC ID', 'pmc_id']
            : ['PMID', 'pmid']);
        const searchable = [
            direct,
            study.Study,
            study.Reference,
            study.Link,
            study.full_text_url,
            study['Full Text Link']
        ].filter(Boolean).join(' ');
        if (isPmcid) {
            const match = searchable.match(/\bPMC\s*:?\s*(\d+)\b/i);
            if (match) return `PMC${match[1]}`;
            return /^\d+$/.test(direct) ? `PMC${direct}` : '';
        }
        if (direct) {
            const directMatch = direct.match(/\d+/);
            if (directMatch) return directMatch[0];
        }
        const match = searchable.match(/(?:\bPMID\s*:?\s*|pubmed\.ncbi\.nlm\.nih\.gov\/)(\d+)\b/i);
        return match ? match[1] : '';
    }

    function csvCell(value) {
        let text = value === undefined || value === null ? '' : String(value);
        if (/^[\s]*[=+@]/.test(text) || (/^[\s]*-/.test(text) && Number.isNaN(Number(text)))) {
            text = `'${text}`;
        }
        return `"${text.replace(/"/g, '""')}"`;
    }

    function exportStudiesToCsv() {
        if (!currentStudies.length) {
            alert(uiText('No studies to export.'));
            return;
        }
        const columns = [
            'Row', 'Selected', 'Study', 'PMID', 'PMCID', 'Effect Type', 'Effect Size',
            'Lower CI', 'Upper CI', 'Sample Size', 'Cases', 'Estimated Cases',
            'Quality Score', 'Verified', 'Exclusion Flags', 'Article', 'Comparison',
            'Design', 'Timing', 'Continent', 'Exposure Measurement', 'Journal', 'Year', 'Link'
        ].map(column => uiText(column));
        const rows = currentStudies.map((study, index) => {
            const checkbox = document.querySelector(`.study-checkbox[data-index="${index}"]`);
            return [
                index + 1,
                uiText(checkbox && checkbox.checked ? 'Yes' : 'No'),
                study.Study,
                studyIdentifier(study, 'PMID'),
                studyIdentifier(study, 'PMCID'),
                study['Effect Type'],
                study['Effect Size'],
                study['Lower CI'],
                study['Upper CI'],
                study.Participants || study['Sample Size'],
                study.Cases,
                study['Estimated Cases'],
                study['Quality Score'],
                study.verifications || 0,
                study.exclusion_flags || 0,
                study.Reference,
                study.comparison_type,
                study.Design,
                study.Timing,
                study.Continent,
                study.exposure_measurement_type || 'unclear',
                study.Journal,
                study.Year,
                study.Link
            ];
        });
        const csv = [columns, ...rows].map(row => row.map(csvCell).join(',')).join('\r\n');
        const blob = new Blob([`\uFEFF${csv}`], { type: 'text/csv;charset=utf-8' });
        const scope = [selectedDiseaseValue(), selectedExposureValue()]
            .filter(Boolean)
            .join('_')
            .toLowerCase()
            .replace(/[^a-z0-9]+/g, '_')
            .replace(/^_+|_+$/g, '');
        const downloadUrl = URL.createObjectURL(blob);
        const anchor = document.createElement('a');
        anchor.href = downloadUrl;
        anchor.download = `metafemina_extracted_studies${scope ? `_${scope}` : ''}.csv`;
        anchor.style.display = 'none';
        document.body.appendChild(anchor);
        anchor.click();
        anchor.remove();
        setTimeout(() => URL.revokeObjectURL(downloadUrl), 0);
    }

    // Select All / Export / Deselect All Buttons
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
    if (elements.exportStudiesBtn) {
        elements.exportStudiesBtn.addEventListener('click', exportStudiesToCsv);
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
        const quality = elements.filterQuality ? elements.filterQuality.value : 'Moderate+';
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
                if (!meetsDefaultJbiThreshold(study)) return false;
            } else if (quality !== 'All' && quality !== 'Fair+' && (study['Quality Score'] || 'Fair') !== quality) return false;
            if (measure !== 'All' && canonicalEffectMeasure(study['Effect Type']) !== measure) return false;
            
            const studyExpType = study.exposure_measurement_type || 'unclear';
            if (exposureType === 'Dietary intake only') {
                if (studyExpType !== 'dietary_intake') return false;
            } else if (exposureType === 'Human biospecimen only') {
                if (studyExpType !== 'human_biospecimen') return false;
            }
            return true;
        });

        sortCurrentStudies();
        renderStudiesTable();
    }

    function selectedDiseaseOption() {
        return elements.disease && elements.disease.selectedOptions
            ? elements.disease.selectedOptions[0]
            : null;
    }

    function selectedDiseaseValue() {
        const option = selectedDiseaseOption();
        return option && option.dataset.disease
            ? option.dataset.disease
            : (elements.disease ? elements.disease.value : '');
    }

    function selectedSubcategoryValue() {
        const option = selectedDiseaseOption();
        return option && option.dataset.subcategory ? option.dataset.subcategory : null;
    }

    function selectedBaselineRisk() {
        const option = selectedDiseaseOption();
        if (option && option.dataset.subcategory) {
            const subtypeLifetimeRiskPercent = Number(option.dataset.risk);
            if (Number.isFinite(subtypeLifetimeRiskPercent) && subtypeLifetimeRiskPercent > 0) {
                return subtypeLifetimeRiskPercent / 100;
            }
        }
        const disease = selectedDiseaseValue().toLowerCase();
        if (disease.includes('uterine') || disease.includes('uterus') || disease.includes('endometrial')) {
            return 0.031;
        }
        if (disease.includes('ovarian') || disease.includes('ovary')) {
            return 0.013;
        }
        return 0.13;
    }

    function updateBaselineIncidence() {
        if (!elements.disease || !elements.pooledIncidence) return;
        elements.pooledIncidence.value = selectedBaselineRisk() * 100;
        updatePooledPowerAnalysis();
    }

    if (elements.disease) {
        elements.disease.addEventListener('change', () => {
            updateBaselineIncidence();
        });
        updateBaselineIncidence();
    }

    if (elements.analyzeBtn) {
        elements.analyzeBtn.addEventListener('click', () => runAnalysis(false));
    }

    function selectedStudiesFromTable() {
        return Array.from(document.querySelectorAll('.study-checkbox'))
            .filter((checkbox) => checkbox.checked)
            .map((checkbox) => currentStudies[Number(checkbox.dataset.index)])
            .filter(Boolean);
    }

    async function requestReanalysis(selectedStudies, analysisContext) {
        const context = analysisContext || lastAnalysisContext || {
            disease: selectedDiseaseValue(),
            exposure: selectedExposureValue()
        };
        const response = await fetch('/reanalyze', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                studies: selectedStudies,
                disease: context.disease,
                exposure: context.exposure,
                outcome: elements.outcome ? elements.outcome.value : 'Incidence',
                exclude_meta: true,
                quality_filter: elements.filterQuality ? elements.filterQuality.value : 'Moderate+'
            })
        });
        const data = await response.json();
        if (!response.ok || data.error) {
            throw new Error(uiText(data.error || `Server returned ${response.status}: ${response.statusText}`));
        }
        return data;
    }

    // Run Analysis Function
    async function runAnalysis(forceRefresh = false) {
        const disease = selectedDiseaseValue();
        const subcategory = selectedSubcategoryValue();
        const exposure = selectedExposureValue();
        const outcome = elements.outcome.value;
        const excludeMeta = true;
        const model = elements.model ? elements.model.value : "openai.gpt-4o";

        if (!disease || !exposure) {
            alert(uiText('Please enter both disease and exposure.'));
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
                    subcategory,
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
                allStudies = Array.isArray(data.studies) ? data.studies : [];
                applyFilters();
                const analysisContext = { disease, exposure };
                let displayedAnalysis = data;

                // Do not expose the cached all-quality result while waiting for
                // the default Moderate+ analysis. The result shown first must
                // already match the checked studies in the filtered table.
                if (!subcategory) {
                    const selectedStudies = selectedStudiesFromTable();
                    if (selectedStudies.length === 0) {
                        throw new Error(uiText('No studies meet the default analysis criteria.'));
                    }
                    displayedAnalysis = await requestReanalysis(selectedStudies, analysisContext);
                }

                updateResultsUI(displayedAnalysis, analysisContext);
                elements.results.classList.remove('hidden');
            }
        } catch (e) {
            elements.errorMsg.textContent = uiText(
                'Error: {message}. Please check your connection and server status.',
                { message: e.message }
            );
            elements.errorMsg.classList.remove('hidden');
            console.error("Analyze error:", e);
        } finally {
            elements.loading.classList.add('hidden');
        }
    }

    // Update (Re-analyze) Logic
    if (elements.updateBtn) {
        elements.updateBtn.addEventListener('click', async () => {
            const selectedStudies = selectedStudiesFromTable();

            if (selectedStudies.length === 0) {
                alert(uiText('Please select at least one study.'));
                return;
            }

            elements.updateBtn.textContent = uiText('Updating...');
            elements.updateBtn.disabled = true;
            const analysisContext = lastAnalysisContext || {
                disease: selectedDiseaseValue(),
                exposure: selectedExposureValue()
            };

            try {
                const data = await requestReanalysis(selectedStudies, analysisContext);
                updateResultsUI(data, analysisContext);
            } catch (e) {
                console.error("Update error:", e);
                alert(`${uiText('Failed to update analysis.')} ${e.message}`);
            } finally {
                elements.updateBtn.textContent = uiText('Update Analysis');
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

            if (study.verification_status === 'review_requested') tr.style.backgroundColor = '#fff8e1';


            // Checkbox logic
            const rawCases = String(study['Cases'] !== undefined && study['Cases'] !== null ? study['Cases'] : '').replace(/,/g, '');
            const casesVal = parseInt(rawCases);
            
            let estCasesVal = parseInt(study['Estimated Cases']);
            if (isNaN(estCasesVal)) {
                const totalN = parseInt(String(study.Participants || study['Sample Size'] || '').replace(/,/g, ''));
                if (!isNaN(totalN)) {
                    const dScope = selectedDiseaseValue().toLowerCase() || 'breast cancer';
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
            const eligibleEffectMeasurement = hasEligibleEffectMeasurement(study);
            const minCases = elements.filterMinCases ? (parseInt(elements.filterMinCases.value) || 0) : 50;
            const qualityScore = String(study['Quality Score'] || 'Fair');
            const qualityIsEligible = meetsDefaultJbiThreshold(study);
            const jbiEntries = itemizedJbiEntries(study);
            const isChecked = (qualityIsEligible && eligibleEffectMeasurement && !isNaN(finalCasesVal) && finalCasesVal > minCases) ? 'checked' : '';

            // Build Exclusion Reason Title
            let unselectedReason = "";
            if (!isChecked) {
                if (!qualityIsEligible) unselectedReason = uiText('Excluded by default: JBI rating is below Moderate');
                else if (!eligibleEffectMeasurement) unselectedReason = uiText('Excluded from meta-analysis: effect measurement must be RR, IRR, OR, or HR');
                else if (isNaN(finalCasesVal)) unselectedReason = uiText('Excluded: Cases not specified or invalid');
                else if (finalCasesVal <= minCases) {
                    const isEst = isNaN(casesVal);
                    unselectedReason = uiText('Excluded: Cases ≤ {minimum}{estimated}', {
                        minimum: minCases,
                        estimated: isEst ? uiText(' (estimated)') : ''
                    });
                }
            }

            if (study.verification_status === 'review_requested') {
                tr.style.backgroundColor = '#fff8e1';
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
                    <a href="${study.Link}" target="_blank" class="notranslate" translate="no" style="color: var(--primary); text-decoration: none; font-weight: 800;">
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
                            <span class="notranslate" translate="no" style="font-size: 0.7em; min-width: 20px;">${study['Effect Type'] || 'OR'}</span>
                            <input type="number" step="0.001" value="${parseFloat(study['Effect Size'] || 1).toFixed(3)}" 
                                   style="width: 60px; font-size: 0.8em;"
                                   onchange="currentStudies[${index}]['Effect Size'] = parseFloat(this.value)">
                        </div>
                        ${(() => {
                            const es = parseFloat(study['Effect Size']);
                            const type = (study['Effect Type'] || 'OR').toUpperCase();
                            if (!isNaN(es)) {
                                const p0 = selectedBaselineRisk();
                                const pctText = (p0 * 100).toFixed(1).replace('.0', '') + '%';
                                if (type === 'OR' || type === 'ODDS RATIO') {
                                    const rr = es / (1 - p0 + (p0 * es));
                                    return `<div style="font-size: 0.65em; color: #777; padding-left: 2px;" title="${uiText('Estimated Relative Risk (assuming {risk} baseline risk)', { risk: pctText })}">${uiText('Est. RR:')} <span class="notranslate" translate="no">${rr.toFixed(3)}</span></div>`;
                                } else if (type === 'HR' || type === 'HAZARD RATIO' || type === 'IRR' || type === 'INCIDENCE RATE RATIO') {
                                    const rr = (1 / p0) * (1 - Math.exp(es * Math.log(1 - p0)));
                                    return `<div style="font-size: 0.65em; color: #777; padding-left: 2px;" title="${uiText('Estimated Relative Risk (assuming {risk} baseline risk)', { risk: pctText })}">${uiText('Est. RR:')} <span class="notranslate" translate="no">${rr.toFixed(3)}</span></div>`;
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
                                            const quality = String(currentStudies[idx]['Quality Score'] || '').trim().toLowerCase();
                                            const qualityEligible = quality === 'good' || quality === 'moderate';
                                            const shouldCheck = qualityEligible && hasEligibleEffectMeasurement(currentStudies[idx]) && !isNaN(finalVal) && finalVal > minC;
                                            cb.checked = shouldCheck;
                                            if(row){ row.style.opacity = shouldCheck ? '' : '0.6'; row.style.backgroundColor = shouldCheck ? '' : 'rgba(200,200,200,0.15)'; }
                                        }
                                    })(this, ${index})">
                        </div>
                    </div>
                </td>
                <td>
                    <div class="quality-badge quality-${qualityScore.toLowerCase()}"
                         tabindex="0" aria-describedby="jbi-item-tooltip"
                         style="font-size: 0.7rem; padding: 2px 6px; border-radius: 12px; color: white;">
                         ${uiText(qualityScore)}
                    </div>
                </td>
                <td>
                    <button onclick="window.verifyStudy('${study.PMID}', this)" style="cursor: pointer;">✓ ${study.verifications || 0}</button>
                </td>
                <td>
                    <button onclick="window.excludeStudy('${study.PMID}', this)" 
                            style="cursor: pointer; background: ${(study.exclusion_flags || 0) > 0 ? '#f57c00' : '#6c757d'}; color: white; border: none; padding: 2px 8px; border-radius: 4px;"
                            title="Flag for developer review (2 flags email developers; results do not change)">
                        ⚑ ${study.exclusion_flags || 0}
                    </button>
                </td>
                <td class="notranslate" translate="no" style="font-size: 0.75em;" title="${unselectedReason}">${study.Reference || '-'}</td>
                <td style="font-size: 0.75em;" title="${unselectedReason}">
                    <b>Context:</b> ${study.comparison_type || '-'}<br>
                    <b>Design:</b> ${study.Design || '-'}<br>
                    <b>Location:</b> ${study.Continent || '-'}<br>
                    <b>Exposure quantification:</b><br>
                    <select onchange="currentStudies[${index}]['exposure_measurement_type'] = this.value; (function(selectEl) {
                        const val = selectEl.value;
                        if (val === 'dietary_intake') selectEl.style.color = '#2e7d32';
                        else if (val === 'human_biospecimen') selectEl.style.color = '#1565c0';
                        else selectEl.style.color = '#e65100';
                    })(this)" style="font-weight: bold; border: 1px solid #ccc; border-radius: 4px; padding: 2px; font-size: 0.8em; max-width: 100%; box-sizing: border-box; color: ${
                        (() => {
                            const t = study.exposure_measurement_type || 'unclear';
                            if (t === 'dietary_intake') return '#2e7d32';
                            if (t === 'human_biospecimen') return '#1565c0';
                            return '#e65100';
                        })()
                    }">
                        <option value="unclear" ${(!study.exposure_measurement_type || study.exposure_measurement_type === 'unclear') ? 'selected' : ''}>Unclear</option>
                        <option value="dietary_intake" ${study.exposure_measurement_type === 'dietary_intake' ? 'selected' : ''}>Dietary</option>
                        <option value="human_biospecimen" ${study.exposure_measurement_type === 'human_biospecimen' ? 'selected' : ''}>Biospecimen</option>
                    </select>
                </td>
                <td class="notranslate" translate="no" style="font-size: 0.75em;" title="${unselectedReason}">${study.Journal || '-'}</td>
                <td class="notranslate" translate="no" style="font-size: 0.75em;" title="${unselectedReason}">${study.Year || '-'}</td>
            `;

            const qualityBadge = tr.querySelector('.quality-badge');
            if (qualityBadge) {
                const showTooltip = () => showJbiTooltip(qualityBadge, qualityScore, jbiEntries);
                qualityBadge.addEventListener('mouseenter', showTooltip);
                qualityBadge.addEventListener('mouseleave', hideJbiTooltip);
                qualityBadge.addEventListener('focus', showTooltip);
                qualityBadge.addEventListener('blur', hideJbiTooltip);
                qualityBadge.addEventListener('keydown', (event) => {
                    if (event.key === 'Escape') {
                        hideJbiTooltip();
                        qualityBadge.blur();
                    }
                });
            }

            // Build Details row
            const detailsTr = document.createElement('tr');
            detailsTr.className = 'details-row hidden';
            detailsTr.id = `details-row-${index}`;
            if (study.verification_status === 'review_requested') detailsTr.style.backgroundColor = '#fff8e1';
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
                <td colspan="14" style="padding: 1.25rem 2rem; border-bottom: 1px solid var(--border);">
                    <div class="snippets-container" style="display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 1.25rem; border-left: 4px solid var(--primary); padding-left: 1.25rem; margin-left: 0.5rem;">
                        <div class="snippet-item" style="display: flex; flex-direction: column; gap: 0.25rem;">
                            <span style="font-weight: 700; color: #555; font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.05em;">Exposure Measurement Explanation</span>
                            <span style="font-size: 0.88rem; font-style: italic; color: #111; line-height: 1.45;">${study.exposure_measurement_supporting_text ? `<span class="notranslate" translate="no">"${study.exposure_measurement_supporting_text}"</span>` : '<i>Not available</i>'}</span>
                        </div>
                        <div class="snippet-item" style="display: flex; flex-direction: column; gap: 0.25rem;">
                            <span style="font-weight: 700; color: #555; font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.05em;">Sample Size Quote</span>
                            <span style="font-size: 0.88rem; font-style: italic; color: #111; line-height: 1.45;">${est.sample_size ? `<span class="notranslate" translate="no">"${est.sample_size}"</span>` : '<i>Not available</i>'}</span>
                        </div>
                        <div class="snippet-item" style="display: flex; flex-direction: column; gap: 0.25rem;">
                            <span style="font-weight: 700; color: #555; font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.05em;">Effect Size Quote</span>
                            <span style="font-size: 0.88rem; font-style: italic; color: #111; line-height: 1.45;">${est.effect_size ? `<span class="notranslate" translate="no">"${est.effect_size}"</span>` : '<i>Not available</i>'}</span>
                        </div>
                        <div class="snippet-item" style="display: flex; flex-direction: column; gap: 0.25rem;">
                            <span style="font-weight: 700; color: #555; font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.05em;">Effect Direction Quote</span>
                            <span style="font-size: 0.88rem; font-style: italic; color: #111; line-height: 1.45;">${est.effect_direction ? `<span class="notranslate" translate="no">"${est.effect_direction}"</span>` : '<i>Not available</i>'}</span>
                        </div>
                        <div class="snippet-item" style="display: flex; flex-direction: column; gap: 0.25rem;">
                            <span style="font-weight: 700; color: #555; font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.05em;">P-Value Quote</span>
                            <span style="font-size: 0.88rem; font-style: italic; color: #111; line-height: 1.45;">${est.p_value ? `<span class="notranslate" translate="no">"${est.p_value}"</span>` : '<i>Not available</i>'}</span>
                        </div>
                        <div class="snippet-item" style="display: flex; flex-direction: column; gap: 0.25rem;">
                            <span style="font-weight: 700; color: #555; font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.05em;">Confidence Interval Quote</span>
                            <span style="font-size: 0.88rem; font-style: italic; color: #111; line-height: 1.45;">${est.confidence_interval ? `<span class="notranslate" translate="no">"${est.confidence_interval}"</span>` : '<i>Not available</i>'}</span>
                        </div>
                        <div class="snippet-item" style="display: flex; flex-direction: column; gap: 0.25rem;">
                            <span style="font-weight: 700; color: #555; font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.05em;">Outcome Definition Quote</span>
                            <span style="font-size: 0.88rem; font-style: italic; color: #111; line-height: 1.45;">${est.outcome_definition ? `<span class="notranslate" translate="no">"${est.outcome_definition}"</span>` : '<i>Not available</i>'}</span>
                        </div>
                        <div class="snippet-item" style="display: flex; flex-direction: column; gap: 0.25rem;">
                            <span style="font-weight: 700; color: #555; font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.05em;">Exposure Definition Quote</span>
                            <span style="font-size: 0.88rem; font-style: italic; color: #111; line-height: 1.45;">${est.exposure_definition ? `<span class="notranslate" translate="no">"${est.exposure_definition}"</span>` : '<i>Not available</i>'}</span>
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
        const study = currentStudies.find(s => String(s.PMID) === String(pmid));
        const disease = selectedDiseaseValue();
        const exposure = selectedExposureValue();
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
                if (study) study.verifications = data.count;
                if (data.review_requested) {
                    if (study) study.verification_status = 'review_requested';
                    btn.style.background = '#f57c00';
                    if (data.notification_sent) {
                        alert(uiText('Two matching submissions were received. Developers have been emailed for review; results remain unchanged.'));
                    } else if (!data.notification_already_sent) {
                        alert(uiText('Developer review was requested, but the notification email could not be sent. Results remain unchanged.'));
                    }
                }
            }
        } catch (e) {
            console.error("Verify error:", e);
        }
    };

    window.excludeStudy = async (pmid, btn) => {
        if (!pmid) return;
        if (!confirm(uiText('Flag this study for developer review? Two flags will email developers but will not change the results.'))) return;

        try {
            const disease = selectedDiseaseValue();
            const exposure = selectedExposureValue();
            const outcome = elements.outcome.value;
            const context_key = `${disease}_${exposure}_${outcome}`.toLowerCase().replace(/ /g, "_");

            const res = await fetch('/exclude', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ pmid, study_data: currentStudies.find(s => String(s.PMID) === String(pmid)), disease, exposure, outcome })
            });
            if (res.ok) {
                const data = await res.json();
                const study = currentStudies.find(s => String(s.PMID) === String(pmid));
                if (study) study.exclusion_flags = data.exclusions;
                btn.textContent = `⚑ ${data.exclusions}`;
                btn.style.background = '#f57c00';
                if (data.review_requested) {
                    if (study) study.verification_status = 'review_requested';
                    if (data.notification_sent) {
                        alert(uiText('The review threshold was reached. Developers have been emailed; results remain unchanged.'));
                    } else if (data.notification_already_sent) {
                        alert(uiText('Developers were already notified about these flags. Results remain unchanged.'));
                    } else {
                        alert(uiText('Developer review was requested, but the notification email could not be sent. Results remain unchanged.'));
                    }
                }
            }
        } catch (e) {
            console.error("Exclude error:", e);
        }
    };

    // Sorting
    function sortCurrentStudies() {
        const field = currentSort.field;
        const qualityOrder = { Good: 0, Moderate: 1, Fair: 2, Poor: 3 };

        currentStudies.sort((a, b) => {
            let valA = a[field], valB = b[field];
            if (field === 'Effect Size') { valA = parseFloat(a[field]); valB = parseFloat(b[field]); }
            if (field === 'Sample Size') {
                valA = parseInt(String(a.Participants || a['Sample Size'] || '').replace(/,/g, ''), 10);
                valB = parseInt(String(b.Participants || b['Sample Size'] || '').replace(/,/g, ''), 10);
                if (Number.isNaN(valA)) valA = currentSort.direction === 'asc' ? Infinity : -Infinity;
                if (Number.isNaN(valB)) valB = currentSort.direction === 'asc' ? Infinity : -Infinity;
            }
            if (field === 'Quality Score') {
                valA = qualityOrder[a[field]] ?? qualityOrder.Fair;
                valB = qualityOrder[b[field]] ?? qualityOrder.Fair;
            }
            if (valA < valB) return currentSort.direction === 'asc' ? -1 : 1;
            if (valA > valB) return currentSort.direction === 'asc' ? 1 : -1;
            return 0;
        });
    }

    window.handleSort = (field) => {
        if (currentSort.field === field) currentSort.direction = currentSort.direction === 'asc' ? 'desc' : 'asc';
        else { currentSort.field = field; currentSort.direction = 'asc'; }

        sortCurrentStudies();
        renderStudiesTable();
    };

    function updateSortIcons() {
        document.querySelectorAll('th.sortable').forEach(th => th.classList.remove('sort-asc', 'sort-desc'));
        const map = { 'Study': 'th-study', 'Effect Size': 'th-es', 'Sample Size': 'th-n-cases', 'Quality Score': 'th-quality', 'Year': 'th-year', 'Journal': 'th-journal' };
        const id = map[currentSort.field];
        if (id) {
            const el = document.getElementById(id);
            if (el) el.classList.add(currentSort.direction === 'asc' ? 'sort-asc' : 'sort-desc');
        }
    }

    function updateLastUpdated(ts = null) {
        if (!elements.lastUpdated) return;
        let date;
        if (ts) {
            if (typeof ts === 'number' || !isNaN(Number(ts))) {
                // It's a Unix timestamp (seconds since epoch)
                date = new Date(Number(ts) * 1000);
            } else if (typeof ts === 'string') {
                // It's a string timestamp (e.g. YYYY-MM-DD HH:MM:SS)
                // Split on non-digit characters to construct a local Date object
                const parts = ts.split(/[- :T]/);
                if (parts.length >= 6) {
                    date = new Date(parts[0], parts[1] - 1, parts[2], parts[3], parts[4], parts[5]);
                } else {
                    const isoStr = ts.replace(' ', 'T');
                    date = new Date(isoStr);
                    if (isNaN(date.getTime())) {
                        date = new Date(ts);
                    }
                }
            }
        } else {
            return;
        }
        elements.lastUpdated.textContent = isNaN(date.getTime()) ? ts : date.toLocaleString();
    }
    function updateResultsUI(data, analysisContext = null) {
        if (analysisContext) {
            lastAnalysisContext = {
                disease: analysisContext.disease,
                exposure: analysisContext.exposure
            };
        }
        if (elements.forestPlot && data.plot_url) elements.forestPlot.src = `/${data.plot_url}?t=${Date.now()}`;
        if (elements.funnelPlot && data.funnel_plot_url) elements.funnelPlot.src = `/${data.funnel_plot_url}?t=${Date.now()}`;

        if (data.headline && elements.headlineResult) {
            elements.headlineResult.classList.remove('hidden');
            elements.pooledEs.textContent = data.headline.pooled_es;
            elements.pooledCi.textContent = `${data.headline.ci_low}, ${data.headline.ci_upp}`;

            // Since the pooled result is now explicitly calculated as an RR in the backend,
            // we no longer need to show the estimated OR/HR conversions for the headline.
            const rrContainer = document.getElementById('estimated-rr-container');
            if (rrContainer) {
                rrContainer.style.display = 'none';
            }

            // Save original data for measure transformation toggle
            lastHeadlineData = JSON.parse(JSON.stringify(data.headline));
            const interpretationCount = String(data.headline.results_interpretation || '').match(
                /^The pooled analysis of (\d+) studies/i
            );
            lastHeadlineStudyCount = Number(data.headline.n_studies)
                || (interpretationCount ? Number(interpretationCount[1]) : null)
                || (Array.isArray(data.studies) ? data.studies.length : null);
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
                    if (elements.looTbody) {
                        elements.looTbody.innerHTML = '';
                        (data.headline.loo_results || []).forEach(res => {
                            const tr = document.createElement('tr');
                            tr.innerHTML = `
                                <td class="notranslate" translate="no">${res.omitted}</td>
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
            thCases.innerHTML = `N<span class="sort-icon"></span> / ${term}`;
        }
    }

    // Measure Transformation Logic
    if (elements.displayMeasure) {
        elements.displayMeasure.addEventListener('change', applyResultMeasureTransformation);
    }

    function applyResultMeasureTransformation() {
        if (!lastHeadlineData || !elements.pooledEs || !elements.pooledCi) return;

        const measure = elements.displayMeasure ? elements.displayMeasure.value : 'RR';
        const savedBaselineRisk = Number(lastHeadlineData.baseline_risk);
        const p0 = Number.isFinite(savedBaselineRisk) && savedBaselineRisk > 0
            ? savedBaselineRisk
            : selectedBaselineRisk();
        let es = parseFloat(lastHeadlineData.pooled_es);
        let low = parseFloat(lastHeadlineData.ci_low);
        let upp = parseFloat(lastHeadlineData.ci_upp);
        let pi_low = lastHeadlineData.pi_low !== undefined && lastHeadlineData.pi_low !== null ? parseFloat(lastHeadlineData.pi_low) : null;
        let pi_upp = lastHeadlineData.pi_upp !== undefined && lastHeadlineData.pi_upp !== null ? parseFloat(lastHeadlineData.pi_upp) : null;

        let label = uiText('Pooled Relative Risk (RR)');

        if (measure === 'OR') {
            label = uiText('Pooled Odds Ratio (OR)');
            es = (es * (1 - p0)) / (1 - es * p0);
            low = (low * (1 - p0)) / (1 - low * p0);
            upp = (upp * (1 - p0)) / (1 - upp * p0);
            if (pi_low !== null) pi_low = (pi_low * (1 - p0)) / (1 - pi_low * p0);
            if (pi_upp !== null) pi_upp = (pi_upp * (1 - p0)) / (1 - pi_upp * p0);
        } else if (measure === 'HR') {
            label = uiText('Pooled Hazard Ratio (HR)');
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

        renderHeadlineInterpretation(measure, es, low, upp);
        renderResultsInterpretation(measure, es, low, upp);
        renderFunnelInterpretation();

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
            effectSelectionText = uiText(' (Lower 95% CI)');
        } else if (effectSelection === 'upper') {
            primaryRR = parseFloat(lastHeadlineData.ci_upp);
            effectSelectionText = uiText(' (Upper 95% CI)');
        } else if (effectSelection === 'pi_lower') {
            primaryRR = parseFloat(lastHeadlineData.pi_low);
            effectSelectionText = uiText(' (Lower 95% PI)');
        } else if (effectSelection === 'pi_upper') {
            primaryRR = parseFloat(lastHeadlineData.pi_upp);
            effectSelectionText = uiText(' (Upper 95% PI)');
        } else {
            primaryRR = parseFloat(lastHeadlineData.pooled_es);
        }
        
        if ((effectSelection === 'pi_lower' && lastHeadlineData.pi_low == null) || 
            (effectSelection === 'pi_upper' && lastHeadlineData.pi_upp == null)) {
            elements.pooledPowerAnalysis.classList.remove('hidden');
            if (elements.pooledPowerEsText) elements.pooledPowerEsText.textContent = "N/A" + effectSelectionText;
            if (elements.pooledPowerNTotal) elements.pooledPowerNTotal.textContent = uiText('N/A (≥3 studies required)');
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
        if (elements.powerTextDisplay) elements.powerTextDisplay.textContent = uiText('{power}% power', { power: (power * 100).toFixed(0) });
        if (elements.sidesTextDisplay) elements.sidesTextDisplay.textContent = uiText(sides === 1 ? 'one-sided' : 'two-sided');
        
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
            per_group_text = uiText('({count} per group)', { count: Math.ceil(n_per_group).toLocaleString() });
        } else {
            // Single arm formula
            const n_single = Math.pow(zAlpha * Math.sqrt(p1 * (1 - p1)) + zBeta * Math.sqrt(p2 * (1 - p2)), 2) / Math.pow(diff, 2);
            total_n = Math.ceil(n_single);
            expected_cases = Math.ceil(total_n * p2);
            per_group_text = uiText('(single arm)');
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

    window.addEventListener('metafemina:languagechange', () => {
        if (elements.updateBtn) {
            elements.updateBtn.textContent = uiText(elements.updateBtn.disabled ? 'Updating...' : 'Update Analysis');
        }
        if (currentStudies.length) renderStudiesTable();
        if (lastHeadlineData) applyResultMeasureTransformation();
    });
});
