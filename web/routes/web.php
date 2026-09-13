<?php

use App\Http\Controllers\AskController;
use App\Http\Controllers\Auth\ForgotPasswordController;
use App\Http\Controllers\Auth\LoginController;
use App\Http\Controllers\Auth\OnboardingController;
use App\Http\Controllers\GoogleConnectionController;
use App\Livewire\Admin\ActivityLogIndex;
use App\Livewire\Admin\GoogleConnectionIndex;
use App\Livewire\Admin\KnowledgeBaseIndex;
use App\Livewire\Admin\UserForm;
use App\Livewire\Admin\UserIndex;
use App\Livewire\Ask;
use Illuminate\Support\Facades\Route;

// The only route the perimeter leaves open (ROADMAP Milestone 6). Every other
// route lands behind auth once the auth port arrives.
Route::get('/health', fn () => response()->json([
    'app' => config('app.name'),
    'status' => 'ok',
]));

// Sign-in: email + password -> emailed 6-digit OTP -> session. Custom flow; Fortify's own
// routes stay ignoreRoutes()'d (see FortifyServiceProvider).
Route::middleware('guest')->group(function () {
    Route::get('/login', [LoginController::class, 'showLogin'])->name('login');
    Route::post('/login', [LoginController::class, 'login'])->middleware('throttle:login')->name('login.attempt');
    Route::get('/login/otp', [LoginController::class, 'showOtp'])->name('otp.show');
    Route::post('/login/otp/verify', [LoginController::class, 'verifyOtp'])->middleware('throttle:two-factor')->name('otp.verify');
    Route::post('/login/otp/resend', [LoginController::class, 'resendOtp'])->middleware('throttle:two-factor')->name('otp.resend');

    Route::get('/forgot-password', [ForgotPasswordController::class, 'showRequestForm'])->name('password.request');
    Route::post('/forgot-password', [ForgotPasswordController::class, 'sendResetLink'])->middleware('throttle:password-reset')->name('password.email');
    Route::get('/reset-password/{token}', [ForgotPasswordController::class, 'showResetForm'])->name('password.reset');
    Route::post('/reset-password', [ForgotPasswordController::class, 'reset'])->middleware('throttle:password-reset')->name('password.update');
});

Route::post('/logout', [LoginController::class, 'logout'])->middleware('auth')->name('logout');

// Onboarding — signed, single-use link mailed on an admin-created account, bound on id.
Route::middleware(['guest', 'signed'])->group(function () {
    Route::get('/onboarding/{user:id}', [OnboardingController::class, 'show'])->name('onboarding.show');
    Route::post('/onboarding/{user:id}', [OnboardingController::class, 'store'])->middleware('throttle:login')->name('onboarding.store');
});

// Signed-in area. This app has no public route (web/plan/webui.md §3) — every page below
// is internal staff tooling.
Route::middleware('auth')->group(function () {
    // The 'ask' rate limit (10/min) is enforced inside Ask::submit() itself, not here —
    // this route is the page load, not the question submission (that's a Livewire
    // action routed through livewire/update, already throttled by 'mutations').
    Route::get('/ask', Ask::class)->name('ask');
    Route::get('/ask/{query}/stream', [AskController::class, 'stream'])->name('ask.stream');
    Route::get('/ask/{query}/export/{format}', [AskController::class, 'export'])->name('ask.export');

    // Phase 2/3 build these for real; stubbed here so the shell/nav/RBAC have somewhere
    // to route to (web/plan/webui.md §1's build order).
    Route::view('/chat', 'stubs.coming-soon', ['feature' => 'Chat'])->name('chat');
    Route::view('/ledger', 'stubs.coming-soon', ['feature' => 'Ledger'])->name('ledger');

    Route::prefix('admin')->name('admin.')->group(function () {
        Route::middleware('privilege:users.manage')->prefix('users')->name('users.')->group(function () {
            Route::get('/', UserIndex::class)->name('index');
            Route::get('/create', UserForm::class)->name('create');
            Route::get('/{user}/edit', UserForm::class)->name('edit');
        });

        Route::middleware('privilege:google.manage')->prefix('google')->name('google.')->group(function () {
            Route::get('/', GoogleConnectionIndex::class)->name('index');
        });

        Route::middleware('privilege:kb.manage')->prefix('knowledge')->name('knowledge.')->group(function () {
            Route::get('/', KnowledgeBaseIndex::class)->name('index');
        });

        Route::middleware('privilege:activity-logs.view')->prefix('activity-logs')->name('activity-logs.')->group(function () {
            Route::get('/', ActivityLogIndex::class)->name('index');
        });
    });

    // An OAuth redirect is a full browser navigation to Google and back — plain routes,
    // not Livewire (web/plan/webui.md §5).
    Route::prefix('google')->middleware('privilege:google.manage')->group(function () {
        Route::get('/connect', [GoogleConnectionController::class, 'connect'])->name('google.connect');
        Route::get('/callback', [GoogleConnectionController::class, 'callback'])->name('google.callback');
    });
});
