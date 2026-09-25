<div class="flex flex-col lg:flex-row gap-4 h-[calc(100vh-11rem)]">
    {{-- Conversation rail --}}
    <div class="lg:w-64 flex-shrink-0 flex flex-col gap-2">
        {{-- Plain navigation, not wire:navigate: sendToOrchestrator() below updates the
             address bar with history.replaceState() after a live send, which Livewire's
             SPA router never sees — a wire:navigate click back to a path it still thinks
             it's already on then silently no-ops. A full page load always works. --}}
        <a href="{{ route('chat') }}"
           class="flex items-center justify-center gap-2 text-sm font-semibold text-govviolet-600 border border-govviolet-200 dark:border-govviolet-800 rounded-lg py-2 hover:bg-govviolet-50 dark:hover:bg-govviolet-900/20 transition-colors">
            <i class="ti ti-plus"></i> New conversation
        </a>
        <div class="flex-1 overflow-y-auto space-y-1">
            @forelse($conversations as $c)
            <div class="group relative flex items-center"
                 wire:key="conversation-{{ $c->id }}"
                 x-data="{
                     menuOpen: false,
                     menuStyle: '',
                     // The menu used to be absolute inside this scrolling rail, so opening it on
                     // a row near the bottom pushed the rail's own scrollable area taller instead
                     // of showing the menu — the list visibly jumped to make room. Teleported to
                     // <body> and positioned fixed from the button's own screen position instead,
                     // so it floats over the page and never touches the rail's scroll height, and
                     // can open upward when there isn't 90px of room below.
                     openMenu(e) {
                         const r = e.currentTarget.getBoundingClientRect();
                         this.menuStyle = (r.bottom + 90 > window.innerHeight)
                             ? `left:${r.right - 176}px; bottom:${window.innerHeight - r.top + 4}px;`
                             : `left:${r.right - 176}px; top:${r.bottom + 4}px;`;
                         this.menuOpen = ! this.menuOpen;
                     },
                 }">
                <a href="{{ route('chat.show', $c) }}"
                   class="flex-1 min-w-0 block pl-3 pr-8 py-2 rounded-lg text-sm truncate {{ $activeConversation?->id === $c->id ? 'bg-govviolet-50 dark:bg-govviolet-900/30 text-govviolet-700 dark:text-govviolet-300 font-medium' : 'text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800' }}">
                    {{ $c->title ?? 'New conversation' }}
                </a>
                {{-- .stop.prevent: this sits on top of the row's own link, and a plain click
                     handler here is not enough insurance against a stray navigation. --}}
                <button x-on:click.stop.prevent="openMenu($event)"
                        class="absolute right-1.5 w-7 h-7 flex items-center justify-center rounded text-slate-400 opacity-60 group-hover:opacity-100 focus-visible:opacity-100 hover:bg-slate-200 dark:hover:bg-slate-700"
                        title="Conversation options">
                    <i class="ti ti-dots-vertical text-base"></i>
                </button>
                <template x-teleport="body">
                    <div x-show="menuOpen" x-cloak x-on:click.outside="menuOpen = false"
                         x-bind:style="menuStyle"
                         class="fixed z-50 w-44 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg shadow-lg py-1 text-xs">
                        <a href="{{ route('chat.export', $c) }}" x-on:click="menuOpen = false"
                           class="block px-3 py-1.5 hover:bg-slate-100 dark:hover:bg-slate-700 text-slate-600 dark:text-slate-300">
                            Export as PDF
                        </a>
                        <button wire:click="deleteConversation('{{ $c->id }}')" x-on:click="menuOpen = false"
                                class="w-full text-left px-3 py-1.5 hover:bg-slate-100 dark:hover:bg-slate-700 text-slate-600 dark:text-slate-300">
                            Delete
                        </button>
                        <button wire:click="confirm('forceDeleteConversation', '{{ $c->id }}', 'Permanently delete this conversation? This cannot be undone.', 'Yes, delete permanently')"
                                x-on:click="menuOpen = false"
                                class="w-full text-left px-3 py-1.5 hover:bg-red-50 dark:hover:bg-red-900/30 text-red-600">
                            Delete permanently
                        </button>
                    </div>
                </template>
            </div>
            @empty
            <p class="text-xs text-slate-400 px-3">No conversations yet.</p>
            @endforelse
        </div>
    </div>

    {{-- Active thread --}}
    <div
        wire:key="thread-{{ $mountedConversationId ?? 'new' }}"
        x-data="chatThread()"
        class="flex-1 min-w-0 flex flex-col bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 overflow-hidden"
    >
        {{-- The composer lives inside this same scrolling element, pinned with
             sticky bottom-0, so it always stays on screen even if the panel's
             height guess above doesn't exactly match the real viewport. --}}
        <div class="flex-1 overflow-y-auto p-4 space-y-4" x-ref="scrollArea">
            @if(! $activeConversation)
            {{-- No border/card chrome here on purpose: a bordered stat-card box next to the
                 composer below reads as a second, competing input rather than a hint pointing
                 at the real one. --}}
            <div class="flex flex-col items-center justify-center text-center py-16 mx-auto max-w-md">
                <div class="w-14 h-14 rounded-full bg-govviolet-100 dark:bg-govviolet-900/40 text-govviolet-600 flex items-center justify-center text-2xl">
                    <i class="ti ti-message-chatbot"></i>
                </div>
                <p class="text-sm text-slate-400 dark:text-slate-500 mt-4">Type a question below to begin.</p>
                <div class="mt-6 space-y-1.5 w-full">
                    <p class="text-xs font-medium text-slate-400 dark:text-slate-500 uppercase tracking-wide">Or try an example</p>
                    @foreach(self::EXAMPLE_QUESTIONS as $ex)
                    <button type="button" wire:click="useExample(@js($ex['question']), @js($ex['chart']))"
                            class="block w-full text-left text-sm text-govviolet-700 dark:text-govviolet-300 hover:bg-govviolet-50 dark:hover:bg-govviolet-900/30 rounded-lg px-3 py-2 transition-colors">
                        {{ $ex['question'] }}
                    </button>
                    @endforeach
                </div>
            </div>
            @else
                @foreach($activeConversation->messages as $m)
                    @if($m->role === 'user')
                    <div wire:key="message-{{ $m->id }}" class="flex flex-col items-end" x-data="{ copied: false }">
                        <div class="bg-govviolet-600 text-white rounded-2xl rounded-br-sm px-4 py-2 max-w-lg text-sm whitespace-pre-wrap">{{ $m->content }}</div>
                        <button x-on:click="navigator.clipboard.writeText(@js($m->content)); copied = true; setTimeout(() => copied = false, 1500)"
                                class="mt-1 text-slate-400 hover:text-slate-600 dark:hover:text-slate-300" title="Copy">
                            <i class="ti text-xs" :class="copied ? 'ti-check' : 'ti-copy'"></i>
                        </button>
                    </div>
                    @else
                    @php
                        $chartCalls = $m->toolCalls->where('tool_name', 'make_chart');
                        $detailCalls = $m->toolCalls->where('tool_name', '!=', 'make_chart');
                    @endphp
                    <div wire:key="message-{{ $m->id }}" class="flex flex-col items-start" x-data="{ copied: false }">
                        <div class="bg-slate-100 dark:bg-slate-900 rounded-2xl rounded-bl-sm px-4 py-2 max-w-lg space-y-3">
                            @if($m->content)
                            <div class="chat-markdown text-sm text-slate-700 dark:text-slate-200" x-init="$el.innerHTML = renderMarkdown(@js($m->content))"></div>
                            @elseif($m->toolCalls->isEmpty())
                            <p class="text-sm text-slate-400 italic">No response was generated for this message.</p>
                            @endif
                            @foreach($chartCalls as $tc)
                                @include('livewire.partials.tool-call-card', ['toolCall' => $tc])
                            @endforeach
                            @if($detailCalls->isNotEmpty())
                            <details class="text-xs">
                                <summary class="cursor-pointer text-slate-400 hover:text-slate-600 dark:hover:text-slate-300 select-none">Show query</summary>
                                <div class="mt-2 space-y-2">
                                    @foreach($detailCalls as $tc)
                                        @include('livewire.partials.tool-call-card', ['toolCall' => $tc])
                                    @endforeach
                                </div>
                            </details>
                            @endif
                        </div>
                        @if($m->content)
                        <button x-on:click="navigator.clipboard.writeText(@js($m->content)); copied = true; setTimeout(() => copied = false, 1500)"
                                class="mt-1 text-slate-400 hover:text-slate-600 dark:hover:text-slate-300" title="Copy">
                            <i class="ti text-xs" :class="copied ? 'ti-check' : 'ti-copy'"></i>
                        </button>
                        @endif
                    </div>
                    @endif
                @endforeach
            @endif

            {{-- Live in-flight turn — shown only while streaming, cleared once the
                 turn's persisted rows come back via syncAfterStream(). Stays mounted
                 on a failed send too (streaming already false by then) so liveError
                 below has something to show instead of vanishing the instant the
                 fetch's finally block flips streaming off. --}}
            <template x-if="streaming || liveError">
                <div class="space-y-4">
                    <div class="flex justify-end">
                        <div class="bg-govviolet-600 text-white rounded-2xl rounded-br-sm px-4 py-2 max-w-lg text-sm whitespace-pre-wrap" x-text="liveUserMessage"></div>
                    </div>
                    <div class="flex justify-start">
                        <div class="bg-slate-100 dark:bg-slate-900 rounded-2xl rounded-bl-sm px-4 py-2 max-w-lg space-y-3">
                            <div class="flex gap-1 py-1" x-show="streaming && ! liveAssistantText && ! liveToolCalls.length">
                                <span class="w-1.5 h-1.5 rounded-full bg-slate-400 animate-bounce" style="animation-delay:0ms"></span>
                                <span class="w-1.5 h-1.5 rounded-full bg-slate-400 animate-bounce" style="animation-delay:150ms"></span>
                                <span class="w-1.5 h-1.5 rounded-full bg-slate-400 animate-bounce" style="animation-delay:300ms"></span>
                            </div>
                            <div class="chat-markdown text-sm text-slate-700 dark:text-slate-200" x-init="$watch('liveAssistantText', () => $el.innerHTML = renderMarkdown(liveAssistantText))"></div>
                            {{-- Tool cards stay visible (not collapsed) while a turn is still in
                                 flight — this is the turn's only progress feedback on a multi-tool
                                 question that can run past a minute, pings included. The persisted
                                 view above collapses them once a turn is done and there is nothing
                                 left to wait on. --}}
                            <template x-for="(tc, i) in liveToolCalls" :key="i">
                                <div class="bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg px-3 py-2 text-xs">
                                    <p class="font-semibold text-slate-500 flex items-center gap-1.5">
                                        <i class="ti" :class="toolIcon(tc.name)"></i>
                                        <span x-text="toolLabel(tc.name)"></span>
                                        <i class="ti ti-loader-2 animate-spin" x-show="!tc.result"></i>
                                        <span class="text-slate-400 font-normal" x-show="!tc.result && tc.pings" x-text="'· still working (' + (tc.pings * 15) + 's)'"></span>
                                    </p>
                                    <p class="text-slate-500 mt-1" x-show="tc.result" x-text="tc.result?.summary"></p>
                                    <div x-show="tc.chart" wire:ignore x-init="$watch('tc.chart', (v) => v && Plotly.newPlot($refs['livechart' + i], JSON.parse(v.plotly_json ?? '{}').data ?? [], JSON.parse(v.plotly_json ?? '{}').layout ?? [], {responsive: true}))" :x-ref="'livechart' + i" style="min-height:280px;"></div>
                                </div>
                            </template>
                            <p class="text-xs text-red-600 dark:text-red-400" x-show="liveError" x-text="liveError"></p>
                        </div>
                    </div>
                </div>
            </template>

            {{-- Composer --}}
            <form wire:submit="send" x-on:submit="onSubmit()"
                  class="sticky bottom-0 -mx-4 -mb-4 mt-2 bg-white dark:bg-slate-800 border-t border-slate-200 dark:border-slate-700 p-3 flex items-end gap-2">
                @if(count($models) > 1)
                <select wire:model="model" class="field-input !w-auto text-xs flex-shrink-0">
                    @foreach($models as $key => $m)
                    <option value="{{ $key }}">{{ $m['label'] }}</option>
                    @endforeach
                </select>
                @endif
                <label class="flex items-center gap-2 text-xs font-medium px-3 py-2.5 rounded-lg border border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-300 flex-shrink-0 cursor-pointer select-none"
                       title="Ask for a chart with this answer, instead of leaving it to the model">
                    <span>Visualize</span>
                    <span class="relative inline-block w-9 h-5 flex-shrink-0">
                        <input type="checkbox" wire:model.live="includeChart" class="sr-only peer">
                        <span class="absolute inset-0 rounded-full bg-slate-300 dark:bg-slate-600 peer-checked:bg-govviolet-600 transition-colors"></span>
                        <span class="absolute top-0.5 left-0.5 w-4 h-4 bg-white rounded-full shadow transition-transform peer-checked:translate-x-4"></span>
                    </span>
                </label>
                <textarea wire:model="message" x-ref="composer" rows="1" placeholder="Ask anything..."
                          x-on:input="autoGrow($el)"
                          x-on:keydown.enter="if (! $event.shiftKey) { $event.preventDefault(); $el.closest('form').requestSubmit(); }"
                          class="field-input flex-1 resize-none max-h-40 overflow-y-auto @error('message') field-error @enderror"></textarea>
                @error('message') <p class="field-err-msg">{{ $message }}</p> @enderror
                <button type="submit" x-show="!streaming" wire:loading.attr="disabled" wire:target="send"
                        class="bg-govviolet-600 hover:bg-govviolet-700 disabled:opacity-50 text-white text-sm font-semibold py-2.5 px-4 rounded-lg transition-colors flex-shrink-0">
                    <i class="ti ti-send"></i>
                </button>
                <button type="button" x-show="streaming" x-cloak x-on:click="stopGenerating()"
                        class="bg-slate-600 hover:bg-slate-700 text-white text-sm font-semibold py-2.5 px-4 rounded-lg transition-colors flex-shrink-0"
                        title="Stop generating">
                    <i class="ti ti-player-stop"></i>
                </button>
            </form>
        </div>
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
            abortController: null,
            currentConversationId: null,
            currentTurnId: null,

            stopGenerating() {
                this.abortController?.abort();
                // The fetch dying no longer cancels the turn on its own (it now
                // survives a dropped connection on purpose, so a Cloudflare-side
                // drop can be resumed) — Stop has to say so to the orchestrator
                // directly.
                this.cancelTurn();
            },

            cancelTurn() {
                if (this.currentConversationId && this.currentTurnId) {
                    fetch(`/chat/${this.currentConversationId}/messages/${this.currentTurnId}/cancel`, {
                        method: 'POST',
                        headers: { 'X-CSRF-TOKEN': document.querySelector('meta[name="csrf-token"]').content },
                    }).catch(() => {});
                }
            },

            toolLabel(name) {
                return { search_knowledge: 'Searched the knowledge base', run_sql_query: 'Ran a query', make_chart: 'Made a chart' }[name] ?? name;
            },
            toolIcon(name) {
                return { search_knowledge: 'ti-book', run_sql_query: 'ti-database', make_chart: 'ti-chart-bar' }[name] ?? 'ti-tool';
            },
            renderMarkdown(text) {
                return DOMPurify.sanitize(marked.parse(text ?? ''));
            },
            autoGrow(el) {
                el.style.height = 'auto';
                el.style.height = el.scrollHeight + 'px';
            },
            onSubmit() {
                this.streaming = true;
                this.liveUserMessage = '';
                this.liveAssistantText = '';
                this.liveToolCalls = [];
                this.liveError = null;
                this.$nextTick(() => this.$refs.composer.style.height = 'auto');
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
            async sendToOrchestrator({ conversationId, message, model, includeChart }) {
                this.liveUserMessage = message;
                this.currentConversationId = conversationId;
                this.currentTurnId = null;
                try {
                    await this.streamFrom(`/chat/${conversationId}/send`, { message, model, includeChart }, () => {
                        history.replaceState(null, '', `/chat/${conversationId}`);
                    });
                } catch (e) {
                    if (e.name !== 'AbortError') await this.reconnectAndStream();
                } finally {
                    this.streaming = false;
                    this.abortController = null;
                    this.$wire.call('syncAfterStream');
                }
            },

            // A dead fetch() here can just be Cloudflare's own ~100s cap on total
            // connection duration, not the turn actually failing — confirmed live on a
            // compound question: the 15s heartbeat pings were still landing right up to
            // the drop. The orchestrator keeps a turn running once started, so this
            // reattaches to it by its turn_id and keeps reading from wherever it left
            // off (MCP_ENGINES.md §Streamed events). Bounded at 5 attempts — each one is
            // itself a full streaming connection that can run up to the same ~100s
            // before needing another reconnect, so 5 covers a turn up to the
            // orchestrator's own ~480s generation ceiling with room to spare.
            async reconnectAndStream(attempt = 1) {
                if (! this.currentTurnId || attempt > 5) {
                    // Giving up has to say so to the orchestrator, not just to this tab —
                    // a turn nobody will ever reattach to otherwise keeps running for
                    // nothing, competing with every other turn (and everyone else's
                    // questions) for the same CPU-only Ollama capacity until it finishes
                    // on its own. Confirmed live: two abandoned turns left running this
                    // way were still occupying Ollama minutes later, at a load average
                    // over 10, degrading an otherwise-healthy turn's own timing enough to
                    // make it miss its own connection window too.
                    this.cancelTurn();
                    this.liveError = 'The connection was interrupted. Please try again.';
                    return;
                }
                await new Promise((resolve) => setTimeout(resolve, 2000));
                // A resume replays the turn's *full* history from its very first event
                // (main.py's _tail_chat_turn always starts at index 0) — whatever the
                // dead connection already applied here has to be cleared first, or the
                // replay would double up on top of it.
                this.liveAssistantText = '';
                this.liveToolCalls = [];
                try {
                    await this.streamFrom(`/chat/${this.currentConversationId}/messages/${this.currentTurnId}/resume`, {});
                } catch (e) {
                    if (e.name !== 'AbortError') await this.reconnectAndStream(attempt + 1);
                }
            },

            async streamFrom(url, body, onConnected) {
                this.abortController = new AbortController();
                const res = await fetch(url, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'Accept': 'application/x-ndjson',
                        'X-CSRF-TOKEN': document.querySelector('meta[name="csrf-token"]').content,
                    },
                    body: JSON.stringify(body),
                    signal: this.abortController.signal,
                });
                onConnected?.(res);

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
            },
            applyEvent(event) {
                if (event.turn_id !== undefined) {
                    // Sent as the very first line of every stream (ChatController's
                    // streamTurn()) — the assistant message's own ULID, needed here so
                    // Stop and a reconnect-after-drop both know which turn to reach.
                    this.currentTurnId = event.turn_id;
                } else if (event.token !== undefined) {
                    this.liveAssistantText += event.token;
                } else if (event.tool_call) {
                    this.liveToolCalls.push({ name: event.tool_call.name, arguments: event.tool_call.arguments, result: null, chart: null });
                } else if (event.tool_result) {
                    const tc = this.liveToolCalls.at(-1);
                    if (tc) tc.result = event.tool_result;
                } else if (event.chart) {
                    const tc = this.liveToolCalls.at(-1);
                    if (tc) tc.chart = event.chart;
                } else if (event.ping) {
                    // The orchestrator sends one of these every ~15s while a tool call
                    // (a SQL plan, a chart render) is still running, purely to keep the
                    // connection alive — surfaced here as an elapsed-time tick so a long
                    // wait reads as "still working" instead of looking stuck.
                    const tc = this.liveToolCalls.at(-1);
                    if (tc && !tc.result) tc.pings = (tc.pings ?? 0) + 1;
                } else if (event.error) {
                    this.liveError = event.error.message ?? 'Something went wrong.';
                }
                this.$nextTick(() => this.$refs.scrollArea.scrollTop = this.$refs.scrollArea.scrollHeight);
            },
        };
    }
</script>
@endpush
