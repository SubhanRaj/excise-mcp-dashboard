@props([
    'title' => 'Dashboard',
    'description' => config('app.name').' — internal analytical tool.',
    'uiPrefs' => null,
])

@php
    $fullTitle = "{$title} | ".config('app.name');
    $metaDesc = Str::limit($description, 200);
@endphp

<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="csrf-token" content="{{ csrf_token() }}">
    <title>{{ $fullTitle }}</title>
    <meta name="description" content="{{ $metaDesc }}">

    {{-- Nothing here is ready for search yet — the public landing page is a placeholder
         and everything else is internal staff tooling. --}}
    <meta name="robots" content="noindex, nofollow">

    <link rel="icon" href="{{ asset('favicon.ico') }}" sizes="any">
    <link rel="icon" type="image/svg+xml" href="{{ asset('assets/img/up-gov-emblem.svg') }}">
    <link rel="icon" type="image/png" sizes="32x32" href="{{ asset('favicon-32.png') }}">
    <link rel="icon" type="image/png" sizes="16x16" href="{{ asset('favicon-16.png') }}">
    <link rel="apple-touch-icon" href="{{ asset('apple-touch-icon.png') }}">
    <link rel="manifest" href="{{ asset('site.webmanifest') }}">
    <meta name="theme-color" content="#4a2bc2">

    {{-- The customization panel's saved prefs, if this request is signed in — seeds the
         client the first time a browser has no local copy yet (a new device, or storage
         cleared), so the login carries the preference rather than a fresh visitor's defaults. --}}
    <script>window.__uiPrefsFromServer = @json($uiPrefs);</script>

    {{-- Anti-flash: runs synchronously before paint to prevent theme flicker, mirroring the
         color_scheme cookie so a server-rendered wire:navigate swap already carries the right
         class. Treats an explicit 'system' value the same as an absent key, so the
         customization panel's three-way Theme control has something to read back. --}}
    <script>
        (function () {
            const html = document.documentElement;
            const cookie = (n) => (document.cookie.match(new RegExp('(?:^|; )' + n + '=([^;]+)')) || [])[1];
            const stored = localStorage.getItem('color_scheme');
            const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
            const isDark = stored === 'dark' || ((! stored || stored === 'system') && prefersDark);
            html.classList.toggle('dark', isDark);
            if (! document.cookie.includes('color_scheme=' + (isDark ? 'dark' : 'light'))) {
                document.cookie = 'color_scheme=' + (isDark ? 'dark' : 'light') + ';path=/;max-age=31536000;SameSite=Lax';
            }
            if (! window.__themeMediaBound) {
                window.__themeMediaBound = true;
                window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', function (e) {
                    if ((localStorage.getItem('color_scheme') || 'system') !== 'system') return;
                    html.classList.toggle('dark', e.matches && ! html.classList.contains('contrast-high'));
                });
            }
        })();
    </script>

    {{-- Display panel (Phase 5 customization panel, CLAUDE.md's Laravel-conventions section):
         font/size/spacing/width/density/accent/contrast/reduce-motion apply via data-*
         attributes and the --ui-font-family/--ui-font-scale/--accent-* CSS vars below.
         localStorage + a mirrored cookie are the fast client echo; users.ui_prefs (saved by
         resources/views/components/customization-panel.blade.php) is the durable copy that
         follows the login. Theme keeps its own color_scheme key above, separate from this
         JSON, so the existing dark-mode toggle and this panel share the same state. --}}
    <script>
        var UI_FONTS = {
            inter: { label: 'Inter', family: "'Inter', system-ui, sans-serif", google: null },
            'noto-sans': { label: 'Noto Sans', family: "'Noto Sans', sans-serif", google: 'https://fonts.googleapis.com/css2?family=Noto+Sans:wght@400;500;600;700&display=swap' },
            merriweather: { label: 'Merriweather', family: "'Merriweather', Georgia, serif", google: 'https://fonts.googleapis.com/css2?family=Merriweather:wght@400;700&display=swap' },
            'space-grotesk': { label: 'Space Grotesk', family: "'Space Grotesk', sans-serif", google: 'https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&display=swap' },
            'jetbrains-mono': { label: 'JetBrains Mono', family: "'JetBrains Mono', monospace", google: 'https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600&display=swap' },
        };
        var UI_PREFS_DEFAULTS = {
            font: 'inter', text_size: 1, line_spacing: 'normal', content_width: 'full',
            table_density: 'comfortable', accent: 'violet', high_contrast: false, reduce_motion: false,
        };

        function uiCookie(name) { return (document.cookie.match(new RegExp('(?:^|; )' + name + '=([^;]+)')) || [])[1]; }
        function setUiCookie(name, value) { document.cookie = name + '=' + encodeURIComponent(value) + ';path=/;max-age=31536000;SameSite=Lax'; }

        function loadUiPrefs() {
            try {
                var raw = localStorage.getItem('ui_prefs') || uiCookie('ui_prefs');
                if (raw) return Object.assign({}, UI_PREFS_DEFAULTS, JSON.parse(decodeURIComponent(raw)));
            } catch (e) { /* corrupt storage — fall through */ }
            if (window.__uiPrefsFromServer) return Object.assign({}, UI_PREFS_DEFAULTS, window.__uiPrefsFromServer);
            return Object.assign({}, UI_PREFS_DEFAULTS);
        }

        function applyUiPrefs(prefs) {
            var html = document.documentElement;
            var font = UI_FONTS[prefs.font] || UI_FONTS.inter;
            if (font.google && ! document.querySelector('link[data-ui-font="' + prefs.font + '"]')) {
                var link = document.createElement('link');
                link.rel = 'stylesheet';
                link.href = font.google;
                link.dataset.uiFont = prefs.font;
                document.head.appendChild(link);
            }
            html.style.setProperty('--ui-font-family', font.family);
            html.style.setProperty('--ui-font-scale', [0.875, 1, 1.125, 1.25, 1.375][prefs.text_size] ?? 1);
            html.setAttribute('data-line-spacing', prefs.line_spacing);
            html.setAttribute('data-content-width', prefs.content_width);
            html.setAttribute('data-table-density', prefs.table_density);
            html.setAttribute('data-accent', prefs.accent);
            html.setAttribute('data-reduce-motion', prefs.reduce_motion ? '1' : '0');
            html.classList.toggle('contrast-high', !! prefs.high_contrast);
            if (prefs.high_contrast) html.classList.remove('dark');
        }

        function saveUiPrefs(patch) {
            var prefs = Object.assign(loadUiPrefs(), patch);
            localStorage.setItem('ui_prefs', JSON.stringify(prefs));
            setUiCookie('ui_prefs', JSON.stringify(prefs));
            applyUiPrefs(prefs);
            fetch('{{ route('account.ui-prefs') }}', {
                method: 'PATCH',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRF-TOKEN': document.querySelector('meta[name="csrf-token"]').content,
                },
                body: JSON.stringify(Object.assign({ theme: localStorage.getItem('color_scheme') || 'system' }, prefs)),
            }).catch(function () { /* the local copy already applied — best-effort sync */ });
            return prefs;
        }

        applyUiPrefs(loadUiPrefs());
    </script>

    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">

    {{-- Tailwind Play CDN — no build step. --}}
    <script src="https://cdn.tailwindcss.com"></script>

    {{-- Tabler Icons webfont, self-hosted (public/vendor/tabler-icons). --}}
    <link rel="stylesheet" href="{{ asset('vendor/tabler-icons/tabler-icons.min.css') }}">

    @livewireStyles

    <script>
        // The customization panel's accent choice (govviolet default, govsaffron the one
        // sanctioned alternate — both already the department's own two-tone palette) swaps
        // the --accent-* custom properties defined below. Routing the govviolet ramp through
        // them means every existing bg-/text-/border-/ring-govviolet-* utility already in the
        // app repaints with it, with no change to the ~20 files that use them.
        function withAccentVar(name) {
            return function (opts) {
                return opts.opacityValue === undefined
                    ? 'rgb(var(' + name + '))'
                    : 'rgb(var(' + name + ') / ' + opts.opacityValue + ')';
            };
        }
        tailwind.config = {
            darkMode: 'class',
            theme: { extend: {
                fontFamily: { sans: ['Inter', 'system-ui', 'sans-serif'] },
                // web/plan/webui.md §3: govviolet/govsaffron are the department's palette
                // regardless of audience — this app has no separate public track, so the one
                // admin shell uses govviolet as its accent.
                colors: {
                    govviolet: {
                        50: withAccentVar('--accent-50'), 100: withAccentVar('--accent-100'), 200: withAccentVar('--accent-200'),
                        300: withAccentVar('--accent-300'), 400: withAccentVar('--accent-400'), 500: withAccentVar('--accent-500'),
                        600: withAccentVar('--accent-600'), 700: withAccentVar('--accent-700'), 800: withAccentVar('--accent-800'),
                        900: withAccentVar('--accent-900'), 950: withAccentVar('--accent-950'),
                    },
                    govsaffron: { 50: '#fff5ea', 100: '#ffebd6', 200: '#ffd9af', 300: '#ffbe6f', 400: '#e89c30', 500: '#c47d00', 600: '#a46800', 700: '#764a00', 800: '#4b2d00', 900: '#281600', 950: '#110700' },
                },
            } },
        }
    </script>

    <style type="text/tailwindcss">
        :root {
            --accent-50: 242 239 255; --accent-100: 220 212 255; --accent-200: 192 179 255;
            --accent-300: 163 145 255; --accent-400: 134 112 255; --accent-500: 106 78 255;
            --accent-600: 74 43 194; --accent-700: 61 35 159; --accent-800: 48 28 125;
            --accent-900: 36 20 92; --accent-950: 26 14 61;
            --ui-font-family: 'Inter', system-ui, sans-serif;
            --ui-font-scale: 1;
        }
        html[data-accent="saffron"] {
            --accent-50: 255 245 234; --accent-100: 255 235 214; --accent-200: 255 217 175;
            --accent-300: 255 190 111; --accent-400: 232 156 48; --accent-500: 196 125 0;
            --accent-600: 164 104 0; --accent-700: 118 74 0; --accent-800: 75 45 0;
            --accent-900: 40 22 0; --accent-950: 17 7 0;
        }
        body { font-family: var(--ui-font-family); }
        main { font-size: calc(1rem * var(--ui-font-scale)); }
        [x-cloak] { display: none !important; }

        .pref-opt { @apply px-2 py-1.5 rounded-lg border border-slate-200 dark:border-slate-700 text-center hover:bg-slate-50 dark:hover:bg-slate-800 text-slate-600 dark:text-slate-300 transition-colors; }
        .pref-opt[aria-pressed="true"] { @apply bg-govviolet-600 text-white border-govviolet-600; }

        /* Reader-controlled line spacing — the customization panel's "Line spacing". */
        html[data-line-spacing="compact"] main { line-height: 1.45; }
        html[data-line-spacing="relaxed"] main { line-height: 1.9; }

        /* Reader-controlled content width. Default ("full") is the unconstrained full-bleed
           main every screen already uses; the other two cap it for a more comfortable line
           length on a wide monitor. */
        html[data-content-width="normal"] main { max-width: 1400px; margin-inline: auto; }
        html[data-content-width="wide"] main { max-width: 1800px; margin-inline: auto; }

        /* Table density — every table's cells app-wide, not just one screen's markup. */
        html[data-table-density="compact"] table :is(td, th) { padding-top: 0.25rem; padding-bottom: 0.25rem; }

        /* Reduce motion also quiets Chat's own bounce-dot typing indicator and spinner
           icons, since both are Tailwind animation utilities and this rule catches every
           animation/transition on the page, not just chat's. */
        html[data-reduce-motion="1"] *, html[data-reduce-motion="1"] *::before, html[data-reduce-motion="1"] *::after {
            animation-duration: 0.001ms !important;
            animation-iteration-count: 1 !important;
            transition-duration: 0.001ms !important;
            scroll-behavior: auto !important;
        }

        /* High contrast renders on the light base only — it never coexists with .dark
           (applyUiPrefs()/setTheme() above both enforce that), so these rules don't have to
           fight dark: utilities. */
        html.contrast-high { color-scheme: light; }
        html.contrast-high body { background: #fff !important; color: #000 !important; }
        html.contrast-high a { color: #0000ee; text-decoration: underline; }
        html.contrast-high :is(.stat-card, .field-input, #sidebar, header, footer, .pref-opt) { background: #fff !important; border-color: #000 !important; color: #000 !important; }
        html.contrast-high :is(h1, h2, h3, th) { color: #000 !important; }

        .nav-link { @apply flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors duration-150 cursor-pointer; }
        .nav-link-active { @apply bg-govviolet-600 text-white font-medium; }
        .nav-link-idle   { @apply text-slate-400 hover:bg-slate-800/70 hover:text-slate-100; }
        .nav-section-label { @apply text-[10px] font-semibold uppercase tracking-widest text-slate-600 px-3 pt-5 pb-1.5 block; }

        .stat-card { @apply bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 p-5 flex items-start gap-4; }
        .stat-icon { @apply w-11 h-11 rounded-lg flex items-center justify-center flex-shrink-0 text-xl; }
        .badge     { @apply inline-flex items-center px-2 py-0.5 rounded text-xs font-medium; }

        .field-label { @apply block text-xs font-semibold text-slate-600 dark:text-slate-400 mb-1.5 uppercase tracking-wide; }
        .field-input { @apply w-full px-3 py-2.5 text-sm bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-lg text-slate-800 dark:text-slate-100 placeholder-slate-400 dark:placeholder-slate-600 focus:outline-none focus:ring-2 focus:ring-govviolet-500 focus:border-transparent transition; }
        .field-error { @apply !border-red-400 !bg-red-50 dark:!bg-red-950/40 focus:!ring-red-400; }
        .field-hint  { @apply text-xs text-slate-400 dark:text-slate-500 mt-1; }
        .field-err-msg { @apply text-xs text-red-600 dark:text-red-400 mt-1; }

        #sidebar { transition: width 280ms cubic-bezier(0.4, 0, 0.2, 1); }
        #sidebar.sidebar-expanded  { width: 16rem; }
        #sidebar.sidebar-collapsed { width: 4rem; }
        #sidebar.sidebar-collapsed .sidebar-text,
        #sidebar.sidebar-collapsed .nav-section-label,
        #sidebar.sidebar-collapsed .sidebar-logo-text,
        #sidebar.sidebar-collapsed .sidebar-user-text { display: none; }
        #sidebar.sidebar-collapsed .nav-link { justify-content: center; padding-left: 0; padding-right: 0; }
    </style>

    @stack('styles')
</head>
