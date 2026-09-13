<!DOCTYPE html>
<html lang="en" class="h-full{{ request()->cookie('color_scheme') === 'dark' ? ' dark' : '' }}">

<x-head title="Enter Code" description="Sign in to {{ config('app.name') }}." />

<body class="bg-slate-100 dark:bg-slate-950 h-full flex items-center justify-center p-4 transition-colors duration-200">

<div class="w-full max-w-md">

    <div class="text-center mb-8">
        <div class="w-14 h-14 rounded-2xl bg-govviolet-600 flex items-center justify-center mx-auto mb-4 shadow-lg">
            <i class="ti ti-shield-lock text-white text-2xl"></i>
        </div>
        <h1 class="text-xl font-bold text-slate-800 dark:text-slate-100">Check your email</h1>
        <p class="text-sm text-slate-400 dark:text-slate-500 mt-1">Enter the 6-digit code we just sent you</p>
    </div>

    <div class="bg-white dark:bg-slate-800 rounded-2xl border border-slate-200 dark:border-slate-700 shadow-sm p-8">

        @if ($errors->any())
        <div class="mb-4 flex items-start gap-2 text-sm text-red-700 dark:text-red-400 bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-700 rounded-lg px-4 py-3">
            <i class="ti ti-alert-circle flex-shrink-0 mt-0.5"></i>
            <span>{{ $errors->first() }}</span>
        </div>
        @endif
        @if (session('flasher'))
        <div class="mb-4 flex items-center gap-2 text-sm text-emerald-700 dark:text-emerald-400 bg-emerald-50 dark:bg-emerald-900/30 border border-emerald-200 dark:border-emerald-700 rounded-lg px-4 py-3">
            <i class="ti ti-circle-check flex-shrink-0"></i>
            {{ session('flasher')->messages()->first()?->message() }}
        </div>
        @endif

        <form method="POST" action="{{ route('otp.verify') }}" x-data="otpForm()" x-init="init()">
            @csrf
            <input type="hidden" name="code" x-ref="code">

            <div class="flex justify-between gap-1.5 sm:gap-2 mb-6" @paste="paste($event)">
                <input type="text" inputmode="numeric" autocomplete="one-time-code" maxlength="1" x-ref="box0" x-model="digits[0]" @input="onInput(0, $event)" @keydown.backspace="onBackspace(0)"
                       class="flex-1 min-w-0 h-12 sm:h-14 text-center text-lg sm:text-xl font-semibold bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-600 rounded-lg text-slate-800 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-govviolet-500 focus:border-transparent">
                <input type="text" inputmode="numeric" autocomplete="one-time-code" maxlength="1" x-ref="box1" x-model="digits[1]" @input="onInput(1, $event)" @keydown.backspace="onBackspace(1)"
                       class="flex-1 min-w-0 h-12 sm:h-14 text-center text-lg sm:text-xl font-semibold bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-600 rounded-lg text-slate-800 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-govviolet-500 focus:border-transparent">
                <input type="text" inputmode="numeric" autocomplete="one-time-code" maxlength="1" x-ref="box2" x-model="digits[2]" @input="onInput(2, $event)" @keydown.backspace="onBackspace(2)"
                       class="flex-1 min-w-0 h-12 sm:h-14 text-center text-lg sm:text-xl font-semibold bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-600 rounded-lg text-slate-800 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-govviolet-500 focus:border-transparent">
                <input type="text" inputmode="numeric" autocomplete="one-time-code" maxlength="1" x-ref="box3" x-model="digits[3]" @input="onInput(3, $event)" @keydown.backspace="onBackspace(3)"
                       class="flex-1 min-w-0 h-12 sm:h-14 text-center text-lg sm:text-xl font-semibold bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-600 rounded-lg text-slate-800 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-govviolet-500 focus:border-transparent">
                <input type="text" inputmode="numeric" autocomplete="one-time-code" maxlength="1" x-ref="box4" x-model="digits[4]" @input="onInput(4, $event)" @keydown.backspace="onBackspace(4)"
                       class="flex-1 min-w-0 h-12 sm:h-14 text-center text-lg sm:text-xl font-semibold bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-600 rounded-lg text-slate-800 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-govviolet-500 focus:border-transparent">
                <input type="text" inputmode="numeric" autocomplete="one-time-code" maxlength="1" x-ref="box5" x-model="digits[5]" @input="onInput(5, $event)" @keydown.backspace="onBackspace(5)"
                       class="flex-1 min-w-0 h-12 sm:h-14 text-center text-lg sm:text-xl font-semibold bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-600 rounded-lg text-slate-800 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-govviolet-500 focus:border-transparent">
            </div>

            <button
                type="submit"
                x-ref="submitBtn"
                class="w-full bg-govviolet-600 hover:bg-govviolet-700 text-white text-sm font-semibold py-2.5 px-4 rounded-lg transition-colors flex items-center justify-center gap-2"
            >
                <i class="ti ti-shield-check"></i>
                Verify &amp; sign in
            </button>
        </form>

        <form method="POST" action="{{ route('otp.resend') }}" class="mt-4 text-center">
            @csrf
            <button type="submit" class="text-sm text-govviolet-600 hover:underline">Resend code</button>
        </form>
    </div>

</div>

<script>
    function otpForm() {
        return {
            digits: ['', '', '', '', '', ''],
            boxes: null,
            init() {
                this.boxes = [this.$refs.box0, this.$refs.box1, this.$refs.box2, this.$refs.box3, this.$refs.box4, this.$refs.box5];
                this.boxes[0]?.focus();
            },
            onInput(i, e) {
                const digitsOnly = e.target.value.replace(/\D/g, '');
                if (digitsOnly.length > 1) {
                    this.fill(digitsOnly);
                    return;
                }
                this.digits[i] = digitsOnly;
                if (digitsOnly && i < 5) this.boxes[i + 1]?.focus();
                this.sync();
            },
            onBackspace(i) {
                if (!this.digits[i] && i > 0) {
                    this.boxes[i - 1]?.focus();
                }
            },
            paste(e) {
                const text = (e.clipboardData || window.clipboardData).getData('text').replace(/\D/g, '').slice(0, 6);
                if (!text) return;
                e.preventDefault();
                this.fill(text);
            },
            fill(text) {
                text = text.slice(0, 6);
                this.digits = text.split('').concat(['', '', '', '', '', '']).slice(0, 6);
                const lastIndex = Math.min(text.length, 6) - 1;
                if (lastIndex >= 0) this.boxes[lastIndex]?.focus();
                this.sync();
            },
            sync() {
                this.$refs.code.value = this.digits.join('');
                if (this.$refs.code.value.length === 6) {
                    this.$refs.submitBtn.click();
                }
            },
        };
    }
</script>

@livewireScripts

</body>
</html>
