<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <style>
        body { font-family: sans-serif; font-size: 11px; color: #1e293b; }
        h1 { font-size: 16px; color: #4a2bc2; margin-bottom: 2px; }
        .meta { color: #64748b; font-size: 10px; margin-bottom: 18px; }
        .message { margin-bottom: 14px; padding-bottom: 14px; border-bottom: 1px solid #e2e8f0; }
        .role { font-weight: bold; font-size: 10px; text-transform: uppercase; margin-bottom: 4px; }
        .role-user { color: #4a2bc2; }
        .role-assistant { color: #334155; }
        .content { white-space: pre-wrap; line-height: 1.5; }
        .tool-call { margin-top: 8px; padding: 6px 8px; background: #f8fafc; border: 1px solid #e2e8f0; font-size: 10px; color: #475569; }
        .tool-call .label { font-weight: bold; }
        .chart-img { max-width: 100%; margin-top: 8px; }
        .empty { color: #94a3b8; font-style: italic; }
    </style>
</head>
<body>
    <h1>{{ $conversation->title ?? 'Chat' }}</h1>
    <p class="meta">Exported {{ now()->ist()->format('d M Y, h:i A') }}</p>

    @forelse($conversation->messages as $message)
    <div class="message">
        <p class="role {{ $message->role === 'user' ? 'role-user' : 'role-assistant' }}">
            {{ $message->role === 'user' ? 'You' : 'Assistant' }}
        </p>

        @if($message->content)
        <p class="content">{{ $message->content }}</p>
        @elseif($message->toolCalls->isEmpty())
        <p class="empty">No response was generated for this message.</p>
        @endif

        @foreach($message->toolCalls as $toolCall)
        <div class="tool-call">
            <span class="label">{{ ['search_knowledge' => 'Searched the knowledge base', 'run_sql_query' => 'Ran a query', 'make_chart' => 'Made a chart'][$toolCall->tool_name] ?? $toolCall->tool_name }}</span>
            @if($toolCall->result_summary['summary'] ?? null)
            <div>{{ $toolCall->result_summary['summary'] }}</div>
            @endif
            @if(isset($chartImages[$toolCall->id]))
            <img class="chart-img" src="data:image/png;base64,{{ $chartImages[$toolCall->id] }}">
            @endif
        </div>
        @endforeach
    </div>
    @empty
    <p class="empty">This conversation has no messages.</p>
    @endforelse
</body>
</html>
