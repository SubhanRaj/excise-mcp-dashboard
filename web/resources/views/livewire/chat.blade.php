<div class="flex flex-col lg:flex-row gap-4 h-[calc(100vh-11rem)]">
    {{-- Conversation rail --}}
    <div class="lg:w-64 flex-shrink-0 flex flex-col gap-2">
        <a href="{{ route('chat') }}" wire:navigate
           class="flex items-center justify-center gap-2 text-sm font-semibold text-govviolet-600 border border-govviolet-200 dark:border-govviolet-800 rounded-lg py-2 hover:bg-govviolet-50 dark:hover:bg-govviolet-900/20 transition-colors">
            <i class="ti ti-plus"></i> New conversation
        </a>
        <div class="flex-1 overflow-y-auto space-y-1">
            @forelse($conversations as $c)
            <a href="{{ route('chat.show', $c) }}" wire:navigate
               class="block px-3 py-2 rounded-lg text-sm truncate {{ $activeConversation?->id === $c->id ? 'bg-govviolet-50 dark:bg-govviolet-900/30 text-govviolet-700 dark:text-govviolet-300 font-medium' : 'text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800' }}">
                {{ $c->title ?? 'New conversation' }}
            </a>
            @empty
            <p class="text-xs text-slate-400 px-3">No conversations yet.</p>
            @endforelse
        </div>
    </div>

    {{-- Active thread --}}
    <div
        wire:key="thread-{{ $activeConversation?->id ?? 'new' }}"
        x-data="chatThread()"
        class="flex-1 min-w-0 flex flex-col bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 overflow-hidden"
    >
        <div class="flex-1 overflow-y-auto p-4 space-y-4" x-ref="scrollArea">
            @if(! $activeConversation)
            <div class="stat-card justify-center text-center flex-col py-16 mx-auto max-w-md">
                <div class="stat-icon bg-govviolet-100 dark:bg-govviolet-900/40 text-govviolet-600 mx-auto">
                    <i class="ti ti-message-chatbot"></i>
                </div>
                <p class="text-sm text-slate-400 dark:text-slate-500 mt-4">Start a conversation.</p>
            </div>
            @else
                @foreach($activeConversation->messages as $m)
                    @if($m->role === 'user')
                    <div class="flex justify-end">
                        <div class="bg-govviolet-600 text-white rounded-2xl rounded-br-sm px-4 py-2 max-w-lg text-sm whitespace-pre-wrap">{{ $m->content }}</div>
                    </div>
                    @else
                    <div class="flex justify-start">
                        <div class="bg-slate-100 dark:bg-slate-900 rounded-2xl rounded-bl-sm px-4 py-2 max-w-lg space-y-3">
                            @foreach($m->toolCalls as $tc)
                                @include('livewire.partials.tool-call-card', ['toolCall' => $tc])
                            @endforeach
                            @if($m->content)
                            <div class="chat-markdown text-sm text-slate-700 dark:text-slate-200" x-init="$el.innerHTML = renderMarkdown(@js($m->content))"></div>
                            @endif
                        </div>
                    </div>
                    @endif
                @endforeach
            @endif

            {{-- Live in-flight turn — shown only while streaming, cleared once the
                 turn's persisted rows come back via syncAfterStream(). --}}
            <template x-if="streaming">
                <div class="space-y-4">
                    <div class="flex justify-end">
                        <div class="bg-govviolet-600 text-white rounded-2xl rounded-br-sm px-4 py-2 max-w-lg text-sm whitespace-pre-wrap" x-text="liveUserMessage"></div>
                    </div>
                    <div class="flex justify-start">
                        <div class="bg-slate-100 dark:bg-slate-900 rounded-2xl rounded-bl-sm px-4 py-2 max-w-lg space-y-3">
                            <template x-for="(tc, i) in liveToolCalls" :key="i">
                                <div class="bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg px-3 py-2 text-xs">
                                    <p class="font-semibold text-slate-500 flex items-center gap-1.5">
                                        <i class="ti" :class="toolIcon(tc.name)"></i>
                                        <span x-text="toolLabel(tc.name)"></span>
                                        <i class="ti ti-loader-2 animate-spin" x-show="!tc.result"></i>
                                    </p>
                                    <p class="text-slate-500 mt-1" x-show="tc.result" x-text="tc.result?.summary"></p>
                                    <div x-show="tc.chart" wire:ignore x-init="$watch('tc.chart', (v) => v && Plotly.newPlot($refs['livechart' + i], JSON.parse(v.plotly_json ?? '{}').data ?? [], JSON.parse(v.plotly_json ?? '{}').layout ?? [], {responsive: true}))" :x-ref="'livechart' + i" style="min-height:280px;"></div>
                                </div>
                            </template>
                            <div class="chat-markdown text-sm text-slate-700 dark:text-slate-200" x-init="$watch('liveAssistantText', () => $el.innerHTML = renderMarkdown(liveAssistantText))"></div>
                            <p class="text-xs text-red-600 dark:text-red-400" x-show="liveError" x-text="liveError"></p>
                        </div>
                    </div>
                </div>
            </template>
        </div>

        {{-- Composer --}}
        <form wire:submit="send" x-on:submit="onSubmit()" class="border-t border-slate-200 dark:border-slate-700 p-3 flex items-end gap-2">
            @if(count($models) > 1)
            <select wire:model="model" class="field-input w-auto text-xs flex-shrink-0">
                @foreach($models as $key => $m)
                <option value="{{ $key }}">{{ $m['label'] }}</option>
                @endforeach
            </select>
            @endif
            <textarea wire:model="message" rows="1" placeholder="Ask anything..."
                      class="field-input flex-1 resize-none @error('message') field-error @enderror"></textarea>
            @error('message') <p class="field-err-msg">{{ $message }}</p> @enderror
            <button type="submit" wire:loading.attr="disabled" wire:target="send"
                    class="bg-govviolet-600 hover:bg-govviolet-700 disabled:opacity-50 text-white text-sm font-semibold py-2.5 px-4 rounded-lg transition-colors flex-shrink-0">
                <i class="ti ti-send"></i>
            </button>
        </form>
    </div>
</div>

@push('scripts')
<script src="https://cdn.jsdelivr.net/npm/plotly.js-dist-min@2/plotly.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/marked@12/marked.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/dompurify@3/dist/purify.min.js"></script>
<style>
    .chat-markdown :where(p) { margin: 0 0 0.5em; }
    .chat-markdown :where(p:last-child) { margin-bottom: 0; }
    .chat-markdown :where(ul, ol) { margin: 0 0 0.5em 1.25em; }
    .chat-markdown :where(pre) { background: rgb(15 23 42 / 0.9); color: #e2e8f0; padding: 0.6em 0.8em; border-radius: 0.5em; overflow-x: auto; font-size: 0.8em; margin: 0.5em 0; }
    .chat-markdown :where(code) { font-family: ui-monospace, monospace; }
    .chat-markdown :where(p code) { background: rgb(100 116 139 / 0.15); padding: 0.1em 0.35em; border-radius: 0.3em; }
</style>
<script>
    function chatThread() {
        return {
            streaming: false,
            liveUserMessage: '',
            liveAssistantText: '',
            liveToolCalls: [],
            liveError: null,

            toolLabel(name) {
                return { search_knowledge: 'Searched the knowledge base', run_sql_query: 'Ran a query', make_chart: 'Made a chart' }[name] ?? name;
            },
            toolIcon(name) {
                return { search_knowledge: 'ti-book', run_sql_query: 'ti-database', make_chart: 'ti-chart-bar' }[name] ?? 'ti-tool';
            },
            renderMarkdown(text) {
                return DOMPurify.sanitize(marked.parse(text ?? ''));
            },
            onSubmit() {
                this.streaming = true;
                this.liveUserMessage = '';
                this.liveAssistantText = '';
                this.liveToolCalls = [];
                this.liveError = null;
            },
            init() {
                // wire:key changes the DOM node (and re-runs init()) on every conversation
                // switch — destroy() below removes this listener so switching conversations
                // repeatedly doesn't pile up duplicate window listeners.
                this._onMessageReady = (e) => this.sendToOrchestrator(e.detail);
                window.addEventListener('chat-message-ready', this._onMessageReady);
            },
            destroy() {
                window.removeEventListener('chat-message-ready', this._onMessageReady);
            },
            async sendToOrchestrator({ conversationId, message, model }) {
                this.liveUserMessage = message;
                try {
                    const res = await fetch(`/chat/${conversationId}/send`, {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'Accept': 'application/x-ndjson',
                            'X-CSRF-TOKEN': document.querySelector('meta[name="csrf-token"]').content,
                        },
                        body: JSON.stringify({ message, model }),
                    });
                    history.replaceState(null, '', `/chat/${conversationId}`);

                    const reader = res.body.getReader();
                    const decoder = new TextDecoder();
                    let buffer = '';
                    while (true) {
                        const { value, done } = await reader.read();
                        if (done) break;
                        buffer += decoder.decode(value, { stream: true });
                        let nl;
                        while ((nl = buffer.indexOf('\n')) !== -1) {
                            const line = buffer.slice(0, nl).trim();
                            buffer = buffer.slice(nl + 1);
                            if (line) this.applyEvent(JSON.parse(line));
                        }
                    }
                } catch (e) {
                    this.liveError = 'The connection was interrupted. Please try again.';
                } finally {
                    this.streaming = false;
                    this.$wire.call('syncAfterStream');
                }
            },
            applyEvent(event) {
                if (event.token !== undefined) {
                    this.liveAssistantText += event.token;
                } else if (event.tool_call) {
                    this.liveToolCalls.push({ name: event.tool_call.name, arguments: event.tool_call.arguments, result: null, chart: null });
                } else if (event.tool_result) {
                    const tc = this.liveToolCalls.at(-1);
                    if (tc) tc.result = event.tool_result;
                } else if (event.chart) {
                    const tc = this.liveToolCalls.at(-1);
                    if (tc) tc.chart = event.chart;
                } else if (event.error) {
                    this.liveError = event.error.message ?? 'Something went wrong.';
                }
                this.$nextTick(() => this.$refs.scrollArea.scrollTop = this.$refs.scrollArea.scrollHeight);
            },
        };
    }
</script>
@endpush
