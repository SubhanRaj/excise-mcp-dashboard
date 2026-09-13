@props([
    'title' => config('app.name'),
    'description' => 'Conversational analytics for UP Excise departmental figures — revenue, dispatches, shop quotas, and enforcement.',
])

<!DOCTYPE html>
<html lang="en" class="h-full{{ request()->cookie('color_scheme') === 'dark' ? ' dark' : '' }}">

<x-head :title="$title" :description="$description" />

<style type="text/tailwindcss">
    /* GIGW/WCAG: a visible, keyboard-reachable skip link and a strong focus ring. */
    .skip-link { @apply sr-only; }
    .skip-link:focus {
        @apply not-sr-only fixed top-2 left-2 z-[100] bg-govviolet-700 text-white px-4 py-2 rounded-md text-sm font-medium;
    }
    a:focus-visible, button:focus-visible { outline: 3px solid #4a2bc2; outline-offset: 2px; border-radius: 2px; }
</style>

<body class="bg-white dark:bg-slate-950 min-h-full flex flex-col text-slate-900 dark:text-slate-100">

<a href="#main-content" class="skip-link">Skip to main content</a>

{{-- Government identity strip, matching the sibling public-facing apps. --}}
<div class="bg-govviolet-900 text-govviolet-100 text-xs">
    <div class="max-w-5xl mx-auto px-4 sm:px-6 min-h-9 py-1 flex flex-wrap items-center justify-between gap-x-4 gap-y-1">
        <span class="font-medium">Government of Uttar Pradesh<span class="hidden sm:inline text-govviolet-300">&nbsp;| उत्तर प्रदेश सरकार</span></span>
        <a href="{{ route('login') }}" wire:navigate class="flex items-center gap-1 px-2 h-6 rounded hover:bg-govviolet-700">
            <i class="ti ti-login text-sm"></i>
            <span>Staff sign-in</span>
        </a>
    </div>
</div>

<header role="banner" class="border-b border-slate-200 dark:border-slate-800">
    <div class="max-w-5xl mx-auto px-4 sm:px-6 py-4 flex items-center gap-3">
        <img src="{{ asset('assets/img/up-gov-emblem.svg') }}" alt="State Emblem of Uttar Pradesh"
             width="44" height="44" class="w-11 h-11 flex-shrink-0 dark:invert">
        <span>
            <span class="block text-sm sm:text-base font-semibold leading-tight">Department of Excise</span>
            <span class="block text-xs text-slate-500 dark:text-slate-400 leading-tight">Government of Uttar Pradesh &middot; आबकारी विभाग</span>
        </span>
    </div>
</header>

<main id="main-content" role="main" class="flex-1 flex items-center">
    {{ $slot }}
</main>

<footer role="contentinfo" class="border-t border-slate-200 dark:border-slate-800">
    <div class="max-w-5xl mx-auto px-4 sm:px-6 py-6">
        <p class="text-xs text-slate-500 dark:text-slate-400">
            &copy; {{ date('Y') }} Government of Uttar Pradesh, Department of Excise.
        </p>
    </div>
</footer>

</body>
</html>
