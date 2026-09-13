@php
    $icons = ['search_knowledge' => 'ti-book', 'run_sql_query' => 'ti-database', 'make_chart' => 'ti-chart-bar'];
    $labels = ['search_knowledge' => 'Searched the knowledge base', 'run_sql_query' => 'Ran a query', 'make_chart' => 'Made a chart'];
@endphp

<div class="bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg px-3 py-2 text-xs" wire:key="toolcall-{{ $toolCall->id }}">
    <p class="font-semibold text-slate-500 flex items-center gap-1.5">
        <i class="ti {{ $icons[$toolCall->tool_name] ?? 'ti-tool' }}"></i>
        {{ $labels[$toolCall->tool_name] ?? $toolCall->tool_name }}
    </p>
    @if($toolCall->result_summary['summary'] ?? null)
    <p class="text-slate-500 mt-1 whitespace-pre-wrap">{{ $toolCall->result_summary['summary'] }}</p>
    @endif
    @if($toolCall->chartArtifact?->spec['plotly_json'] ?? null)
    <div wire:ignore.self x-init="Plotly.newPlot($el, @js(json_decode($toolCall->chartArtifact->spec['plotly_json'], true)['data'] ?? []), @js(json_decode($toolCall->chartArtifact->spec['plotly_json'], true)['layout'] ?? []), {responsive: true})" style="width:100%;min-height:280px;" class="mt-2"></div>
    @endif
</div>
