<!DOCTYPE html>
<html lang="en" class="h-full{{ request()->cookie('color_scheme') === 'dark' ? ' dark' : '' }}">

<x-head title="Forgot Password" description="Reset your {{ config('app.name') }} password." />

<body class="bg-slate-100 dark:bg-slate-950 h-full flex items-center justify-center p-4 transition-colors duration-200">

<div class="w-full max-w-md">
    <div class="text-center mb-8">
        <div class="w-14 h-14 rounded-2xl bg-govviolet-600 flex items-center justify-center mx-auto mb-4 shadow-lg">
            <i class="ti ti-key text-white text-2xl"></i>
        </div>
        <h1 class="text-xl font-bold text-slate-800 dark:text-slate-100">Reset your password</h1>
        <p class="text-sm text-slate-400 dark:text-slate-500 mt-1">We'll email you a link to set a new one</p>
    </div>

    <div class="bg-white dark:bg-slate-800 rounded-2xl border border-slate-200 dark:border-slate-700 shadow-sm p-8">
        @if($errors->any())
        <div class="mb-4 flex items-start gap-2 text-sm text-red-700 dark:text-red-400 bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-700 rounded-lg px-4 py-3">
            <i class="ti ti-alert-circle flex-shrink-0 mt-0.5"></i><span>{{ $errors->first() }}</span>
        </div>
        @endif

        <form method="POST" action="{{ route('password.email') }}" class="space-y-4">
            @csrf
            <div>
                <label for="email" class="field-label">Email address</label>
                <input id="email" name="email" type="email" value="{{ old('email') }}" required autofocus
                    autocomplete="email" class="field-input @error('email') field-error @enderror">
            </div>
            <button type="submit" class="w-full bg-govviolet-600 hover:bg-govviolet-700 text-white text-sm font-semibold py-2.5 px-4 rounded-lg transition-colors flex items-center justify-center gap-2">
                <i class="ti ti-send"></i> Send reset link
            </button>
        </form>

        <p class="text-center text-sm text-slate-400 dark:text-slate-500 mt-5">
            <a href="{{ route('login') }}" class="text-govviolet-600 hover:underline">Back to sign in</a>
        </p>
    </div>
</div>

</body>
</html>
