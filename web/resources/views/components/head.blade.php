@props([
    'title' => 'Dashboard',
    'description' => config('app.name').' — internal analytical tool.',
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

    {{-- Every route in this app is internal staff tooling — never indexed. --}}
    <meta name="robots" content="noindex, nofollow">

    {{-- Anti-flash: runs synchronously before paint to prevent theme flicker, mirroring the
         color_scheme cookie so a server-rendered wire:navigate swap already carries the right
         class. --}}
    <script>
        (function () {
            const html = document.documentElement;
            const cookie = (n) => (document.cookie.match(new RegExp('(?:^|; )' + n + '=([^;]+)')) || [])[1];
            const stored = localStorage.getItem('color_scheme');
            const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
            const isDark = stored === 'dark' || (stored !== 'light' && prefersDark);
            html.classList.toggle('dark', isDark);
            if (! document.cookie.includes('color_scheme=' + (isDark ? 'dark' : 'light'))) {
                document.cookie = 'color_scheme=' + (isDark ? 'dark' : 'light') + ';path=/;max-age=31536000;SameSite=Lax';
            }
        })();
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
        tailwind.config = {
            darkMode: 'class',
            theme: { extend: {
                fontFamily: { sans: ['Inter', 'system-ui', 'sans-serif'] },
                // web/plan/webui.md §3: govviolet/govsaffron are the department's palette
                // regardless of audience — this app has no separate public track, so the one
                // admin shell uses govviolet as its accent rather than a generic indigo.
                colors: {
                    govviolet: { 50: '#f2efff', 100: '#dcd4ff', 200: '#c0b3ff', 300: '#a391ff', 400: '#8670ff', 500: '#6a4eff', 600: '#4a2bc2', 700: '#3d239f', 800: '#301c7d', 900: '#24145c', 950: '#1a0e3d' },
                    govsaffron: { 50: '#fff5ea', 100: '#ffebd6', 200: '#ffd9af', 300: '#ffbe6f', 400: '#e89c30', 500: '#c47d00', 600: '#a46800', 700: '#764a00', 800: '#4b2d00', 900: '#281600', 950: '#110700' },
                },
            } },
        }
    </script>

    <style type="text/tailwindcss">
        body { font-family: 'Inter', system-ui, sans-serif; }
        [x-cloak] { display: none !important; }

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
