@props([
    'pageTitle' => 'Dashboard',
    'pageSubtitle' => 'UP Department of Excise — MCP Dashboard',
])

<header class="bg-white dark:bg-slate-900 border-b border-slate-200 dark:border-slate-700 px-3 sm:px-6 py-3.5 flex items-center justify-between flex-shrink-0 sticky top-0 z-30">
    <div class="flex items-center gap-3 min-w-0">
        <button onclick="window.toggleMobileSidebar()"
            class="md:hidden w-9 h-9 flex-shrink-0 flex items-center justify-center rounded-lg text-slate-500 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
            title="Menu">
            <i class="ti ti-menu-2 text-lg"></i>
        </button>

        <div class="min-w-0">
            <h1 class="text-base font-semibold text-slate-800 dark:text-slate-100 line-clamp-2 sm:truncate break-words">{{ $pageTitle }}</h1>
            <p class="text-xs text-slate-400 dark:text-slate-500 mt-0.5 truncate hidden sm:block">{{ $pageSubtitle }}</p>
        </div>
    </div>

    <div class="flex items-center gap-2 flex-shrink-0">
        <button onclick="window.toggleDarkMode()" id="dark-mode-btn"
            class="w-9 h-9 flex-shrink-0 flex items-center justify-center rounded-lg text-slate-500 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
            title="Toggle dark mode">
            <i id="dark-mode-icon" class="ti ti-moon text-base"></i>
        </button>
    </div>
</header>
