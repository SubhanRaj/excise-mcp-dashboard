<x-public-layout>
    <div class="max-w-5xl mx-auto px-4 sm:px-6 py-20 sm:py-28 text-center">
        <div class="stat-icon bg-govviolet-100 dark:bg-govviolet-900/40 text-govviolet-600 mx-auto w-16 h-16 text-2xl">
            <i class="ti ti-chart-dots-3"></i>
        </div>
        <h1 class="mt-6 text-2xl sm:text-3xl font-semibold">UP Excise MCP Dashboard</h1>
        <p class="mt-3 text-sm sm:text-base text-slate-500 dark:text-slate-400 max-w-xl mx-auto">
            Ask a question in plain language and get a chart, a table, and the SQL behind it —
            built for the Department of Excise's own analysts.
        </p>
        <p class="mt-1 text-sm text-slate-400 dark:text-slate-500">Coming soon.</p>
        <a href="{{ route('login') }}" wire:navigate
           class="inline-flex items-center gap-2 mt-8 bg-govviolet-600 hover:bg-govviolet-700 text-white text-sm font-semibold py-2.5 px-5 rounded-lg transition-colors">
            <i class="ti ti-login"></i> Staff sign-in
        </a>
    </div>
</x-public-layout>
