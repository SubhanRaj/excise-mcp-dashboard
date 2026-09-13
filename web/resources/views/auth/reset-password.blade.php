<!DOCTYPE html>
<html lang="en" class="h-full{{ request()->cookie('color_scheme') === 'dark' ? ' dark' : '' }}">

<x-head title="Set New Password" description="Set a new {{ config('app.name') }} password." />

<body class="bg-slate-100 dark:bg-slate-950 h-full flex items-center justify-center p-4 transition-colors duration-200">

<div class="w-full max-w-md">
    <div class="text-center mb-8">
        <div class="w-14 h-14 rounded-2xl bg-govviolet-600 flex items-center justify-center mx-auto mb-4 shadow-lg">
            <i class="ti ti-lock-check text-white text-2xl"></i>
        </div>
        <h1 class="text-xl font-bold text-slate-800 dark:text-slate-100">Choose a new password</h1>
    </div>

    <div class="bg-white dark:bg-slate-800 rounded-2xl border border-slate-200 dark:border-slate-700 shadow-sm p-8">
        @if($errors->any())
        <div class="mb-4 flex items-start gap-2 text-sm text-red-700 dark:text-red-400 bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-700 rounded-lg px-4 py-3">
            <i class="ti ti-alert-circle flex-shrink-0 mt-0.5"></i><span>{{ $errors->first() }}</span>
        </div>
        @endif

        <form method="POST" action="{{ route('password.update') }}" class="space-y-4">
            @csrf
            <input type="hidden" name="token" value="{{ $token }}">
            <div>
                <label for="email" class="field-label">Email address</label>
                <input id="email" name="email" type="email" value="{{ old('email', $email) }}" required
                    autocomplete="email" class="field-input @error('email') field-error @enderror">
            </div>
            <div>
                <label for="password" class="field-label">New password</label>
                <input id="password" name="password" type="password" required autocomplete="new-password"
                    class="field-input @error('password') field-error @enderror">
                <p class="field-hint">At least 8 characters, with upper and lower case, a number, and a symbol.</p>
            </div>
            <div>
                <label for="password_confirmation" class="field-label">Confirm new password</label>
                <input id="password_confirmation" name="password_confirmation" type="password" required autocomplete="new-password" class="field-input">
            </div>
            <button type="submit" class="w-full bg-govviolet-600 hover:bg-govviolet-700 text-white text-sm font-semibold py-2.5 px-4 rounded-lg transition-colors flex items-center justify-center gap-2">
                <i class="ti ti-lock-check"></i> Reset password
            </button>
        </form>
    </div>
</div>

</body>
</html>
