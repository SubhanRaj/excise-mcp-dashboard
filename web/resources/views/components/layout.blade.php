@props([
    'title' => 'Dashboard',
    'pageTitle' => 'Dashboard',
    'pageSubtitle' => 'UP Department of Excise — MCP Dashboard',
])

<!DOCTYPE html>
<html lang="en" class="h-full{{ request()->cookie('color_scheme') === 'dark' ? ' dark' : '' }}">

<x-head :title="$title" :description="$pageSubtitle" :ui-prefs="auth()->user()?->ui_prefs" />

<body class="bg-slate-100 dark:bg-slate-950 h-full transition-colors duration-200">
<div class="flex h-screen overflow-hidden">

    <x-sidebar />

    <div id="sidebar-backdrop" onclick="window.toggleMobileSidebar()"
         class="fixed inset-0 bg-black/50 z-40 hidden md:hidden"></div>

    <div class="flex-1 flex flex-col min-w-0 overflow-y-auto">

        <x-header :page-title="$pageTitle" :page-subtitle="$pageSubtitle" />

        <main class="flex-1 p-3 sm:p-6">
            {{ $slot }}
        </main>

        <x-footer />

    </div>
</div>

{{-- Sidebar tooltip bubble — positioned by JS, escapes the sidebar's own overflow
     clipping. Only shown while the sidebar is collapsed (icon-only nav, no room
     for the label itself to stay visible). --}}
<div id="nav-tooltip-bubble"
     style="display:none;position:fixed;z-index:9999;pointer-events:none;transform:translateY(-50%)"
     class="px-2.5 py-1.5 text-xs font-medium text-slate-100 bg-slate-800 rounded-md shadow-lg whitespace-nowrap">
</div>

<x-customization-panel />

@flasher_render

@stack('scripts')

<script>
if (! window.__layoutScriptsInitialized) {
window.__layoutScriptsInitialized = true;

window.toggleDarkMode = function () {
    const isDark = document.documentElement.classList.toggle('dark');
    localStorage.setItem('color_scheme', isDark ? 'dark' : 'light');
    document.cookie = 'color_scheme=' + (isDark ? 'dark' : 'light') + ';path=/;max-age=31536000;SameSite=Lax';
    updateDarkIcon();
};

function updateDarkIcon() {
    const icon = document.getElementById('dark-mode-icon');
    if (!icon) return;
    icon.className = document.documentElement.classList.contains('dark') ? 'ti ti-sun text-base' : 'ti ti-moon text-base';
}

window.toggleMobileSidebar = function () {
    const sidebar  = document.getElementById('sidebar');
    const backdrop = document.getElementById('sidebar-backdrop');
    sidebar.classList.toggle('-translate-x-full');
    sidebar.classList.toggle('translate-x-0');
    backdrop.classList.toggle('hidden');
};

window.toggleSidebar = function () {
    const sidebar   = document.getElementById('sidebar');
    const collapsed = sidebar.classList.contains('sidebar-collapsed');
    sidebar.classList.toggle('sidebar-collapsed', !collapsed);
    sidebar.classList.toggle('sidebar-expanded',   collapsed);
    localStorage.setItem('sidebar_collapsed', collapsed ? '0' : '1');
    document.cookie = 'sidebar_collapsed=' + (collapsed ? '0' : '1') + ';path=/;max-age=31536000;SameSite=Lax';
    updateSidebarIcon();
    updateToggleTooltip(!collapsed);
    hideTooltip();
};

function updateSidebarIcon() {
    const icon    = document.getElementById('sidebar-toggle-icon');
    const sidebar = document.getElementById('sidebar');
    if (!icon) return;
    const collapsed = sidebar.classList.contains('sidebar-collapsed');
    icon.className  = collapsed
        ? 'ti ti-layout-sidebar-left-expand w-5 text-center text-base flex-shrink-0'
        : 'ti ti-layout-sidebar-left-collapse w-5 text-center text-base flex-shrink-0';
}

function updateToggleTooltip(collapsed) {
    const btn = document.getElementById('sidebar-toggle');
    if (btn) btn.dataset.tooltip = collapsed ? 'Expand sidebar' : 'Collapse sidebar';
}

// ── Sidebar tooltips (fixed-position, escapes the sidebar's own overflow
// clipping) — the only way to tell one icon-only nav item from another once
// the sidebar is collapsed, since data-tooltip is not a native browser tooltip.
const tooltipEl = document.getElementById('nav-tooltip-bubble');

function showTooltip(el) {
    const sidebar = document.getElementById('sidebar');
    if (!sidebar || !sidebar.classList.contains('sidebar-collapsed')) return;
    const label = el.dataset.tooltip;
    if (!label || !tooltipEl) return;
    const rect = el.getBoundingClientRect();
    tooltipEl.textContent = label;
    tooltipEl.style.left  = (rect.right + 10) + 'px';
    tooltipEl.style.top   = (rect.top + rect.height / 2) + 'px';
    tooltipEl.style.display = 'block';
}

function hideTooltip() {
    if (tooltipEl) tooltipEl.style.display = 'none';
}

function initTooltips() {
    document.querySelectorAll('#sidebar [data-tooltip]').forEach(function (el) {
        if (el.dataset.tooltipBound) return;
        el.dataset.tooltipBound = '1';
        el.addEventListener('mouseenter', function () { showTooltip(el); });
        el.addEventListener('mouseleave', hideTooltip);
        el.addEventListener('click',      hideTooltip);
    });
}

document.addEventListener('livewire:navigated', function () {
    const storedScheme = localStorage.getItem('color_scheme');
    const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    document.documentElement.classList.toggle('dark', storedScheme === 'dark' || (!storedScheme && prefersDark));

    if (localStorage.getItem('sidebar_collapsed') === '1') {
        const sidebar = document.getElementById('sidebar');
        if (sidebar) {
            sidebar.classList.remove('sidebar-expanded');
            sidebar.classList.add('sidebar-collapsed');
        }
    }
    updateSidebarIcon();
    updateDarkIcon();
    initTooltips();

    document.querySelectorAll('#sidebar a, #sidebar button[type="submit"]').forEach(function (el) {
        el.addEventListener('click', function () {
            if (window.innerWidth < 768) window.toggleMobileSidebar();
        });
    });
});

}
</script>

@livewireScripts

</body>
</html>
