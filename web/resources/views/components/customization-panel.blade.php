{{-- The Phase 5 "Display" panel (CLAUDE.md's Laravel-conventions section, EVALUATION.md §4).
     A FAB in the corner of every authed screen; loadUiPrefs()/applyUiPrefs()/saveUiPrefs()
     and the font catalogue it reads from are defined once in <x-head>, since the anti-flash
     script there needs them before this component even mounts. --}}
<div x-data="{
        open: false,
        prefs: loadUiPrefs(),
        theme: localStorage.getItem('color_scheme') || 'system',
        fonts: UI_FONTS,
        sizeLabels: ['A-', 'A', 'A+', 'A++', 'A+++'],
        setTheme(value) {
            this.theme = value;
            localStorage.setItem('color_scheme', value);
            const dark = value === 'dark' || (value === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches);
            if (! this.prefs.high_contrast) document.documentElement.classList.toggle('dark', dark);
            setUiCookie('color_scheme', dark ? 'dark' : 'light');
            this.prefs = saveUiPrefs(this.prefs);
        },
        set(key, value) {
            this.prefs[key] = value;
            this.prefs = saveUiPrefs(this.prefs);
        },
        reset() {
            this.prefs = Object.assign({}, UI_PREFS_DEFAULTS);
            this.setTheme('system');
        },
    }"
    class="fixed bottom-4 right-4 z-40 print:hidden"
>
    <div x-show="open" x-cloak x-on:click.outside="open = false" x-transition.origin.bottom.right
         class="absolute bottom-14 right-0 w-72 max-h-[75vh] overflow-y-auto rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 shadow-2xl p-4 space-y-4 text-xs">
        <div class="flex items-center justify-between">
            <p class="font-semibold text-slate-900 dark:text-white text-sm">Display</p>
            <div class="flex items-center gap-3">
                <button type="button" x-on:click="reset()" class="text-slate-400 hover:text-slate-600 dark:hover:text-slate-300 flex items-center gap-1">
                    <i class="ti ti-rotate-2"></i> Reset
                </button>
                <button type="button" x-on:click="open = false" aria-label="Close display settings" class="text-slate-400 hover:text-slate-600 dark:hover:text-slate-300">
                    <i class="ti ti-x"></i>
                </button>
            </div>
        </div>

        <div role="group" aria-label="Theme">
            <p class="text-slate-500 dark:text-slate-400 mb-1">Theme</p>
            <div class="grid grid-cols-3 gap-1">
                <button type="button" x-on:click="setTheme('light')" :aria-pressed="theme === 'light'" class="pref-opt">Light</button>
                <button type="button" x-on:click="setTheme('system')" :aria-pressed="theme === 'system'" class="pref-opt">System</button>
                <button type="button" x-on:click="setTheme('dark')" :aria-pressed="theme === 'dark'" class="pref-opt">Dark</button>
            </div>
        </div>

        <div role="group" aria-label="Font family">
            <p class="text-slate-500 dark:text-slate-400 mb-1">Font</p>
            <div class="grid grid-cols-2 gap-1">
                <template x-for="(font, key) in fonts" :key="key">
                    <button type="button" x-on:click="set('font', key)" :aria-pressed="prefs.font === key"
                            :style="{ fontFamily: font.family }" x-text="font.label" class="pref-opt truncate"></button>
                </template>
            </div>
        </div>

        <div role="group" aria-label="Text size">
            <p class="text-slate-500 dark:text-slate-400 mb-1">Text size</p>
            <div class="grid grid-cols-5 gap-1">
                <template x-for="i in [0, 1, 2, 3, 4]" :key="i">
                    <button type="button" x-on:click="set('text_size', i)" :aria-pressed="prefs.text_size === i" x-text="sizeLabels[i]" class="pref-opt"></button>
                </template>
            </div>
        </div>

        <div role="group" aria-label="Line spacing">
            <p class="text-slate-500 dark:text-slate-400 mb-1">Line spacing</p>
            <div class="grid grid-cols-3 gap-1">
                <button type="button" x-on:click="set('line_spacing', 'compact')" :aria-pressed="prefs.line_spacing === 'compact'" class="pref-opt">Compact</button>
                <button type="button" x-on:click="set('line_spacing', 'normal')" :aria-pressed="prefs.line_spacing === 'normal'" class="pref-opt">Normal</button>
                <button type="button" x-on:click="set('line_spacing', 'relaxed')" :aria-pressed="prefs.line_spacing === 'relaxed'" class="pref-opt">Relaxed</button>
            </div>
        </div>

        <div role="group" aria-label="Content width">
            <p class="text-slate-500 dark:text-slate-400 mb-1">Content width</p>
            <div class="grid grid-cols-3 gap-1">
                <button type="button" x-on:click="set('content_width', 'normal')" :aria-pressed="prefs.content_width === 'normal'" class="pref-opt">Normal</button>
                <button type="button" x-on:click="set('content_width', 'wide')" :aria-pressed="prefs.content_width === 'wide'" class="pref-opt">Wide</button>
                <button type="button" x-on:click="set('content_width', 'full')" :aria-pressed="prefs.content_width === 'full'" class="pref-opt">Full</button>
            </div>
        </div>

        <div role="group" aria-label="Table density">
            <p class="text-slate-500 dark:text-slate-400 mb-1">Table density</p>
            <div class="grid grid-cols-2 gap-1">
                <button type="button" x-on:click="set('table_density', 'comfortable')" :aria-pressed="prefs.table_density === 'comfortable'" class="pref-opt">Comfortable</button>
                <button type="button" x-on:click="set('table_density', 'compact')" :aria-pressed="prefs.table_density === 'compact'" class="pref-opt">Compact</button>
            </div>
        </div>

        <div role="group" aria-label="Accent colour">
            <p class="text-slate-500 dark:text-slate-400 mb-1">Accent</p>
            <div class="flex gap-2">
                <button type="button" x-on:click="set('accent', 'violet')" :aria-pressed="prefs.accent === 'violet'" title="Violet" aria-label="Violet"
                        style="background-color: #4a2bc2" class="w-7 h-7 rounded-full"
                        :class="prefs.accent === 'violet' ? 'ring-2 ring-offset-2 ring-slate-900 dark:ring-white dark:ring-offset-slate-900' : ''"></button>
                <button type="button" x-on:click="set('accent', 'saffron')" :aria-pressed="prefs.accent === 'saffron'" title="Saffron" aria-label="Saffron"
                        class="w-7 h-7 rounded-full bg-govsaffron-600"
                        :class="prefs.accent === 'saffron' ? 'ring-2 ring-offset-2 ring-slate-900 dark:ring-white dark:ring-offset-slate-900' : ''"></button>
            </div>
        </div>

        <label class="flex items-center gap-2 pt-1 border-t border-slate-100 dark:border-slate-800 cursor-pointer">
            <input type="checkbox" :checked="prefs.high_contrast" x-on:change="set('high_contrast', $event.target.checked)" class="rounded border-slate-300 dark:border-slate-600 text-govviolet-600 focus:ring-govviolet-500">
            <span>High contrast</span>
        </label>

        <label class="flex items-center gap-2 cursor-pointer" title="Also stops Chat's streaming reply from animating in">
            <input type="checkbox" :checked="prefs.reduce_motion" x-on:change="set('reduce_motion', $event.target.checked)" class="rounded border-slate-300 dark:border-slate-600 text-govviolet-600 focus:ring-govviolet-500">
            <span>Reduce motion</span>
        </label>
    </div>

    <button type="button" x-on:click="open = ! open" aria-label="Display settings" aria-haspopup="true" :aria-expanded="open" title="Display settings"
            class="w-11 h-11 rounded-full shadow-lg flex items-center justify-center border transition-colors"
            :class="open ? 'bg-govviolet-600 text-white border-transparent' : 'bg-white dark:bg-slate-800 text-slate-600 dark:text-slate-300 border-slate-200 dark:border-slate-700 hover:shadow-xl'">
        <i class="ti ti-adjustments-horizontal text-lg"></i>
    </button>
</div>
