<?php

namespace App\Providers;

use App\Models\ActivityLog;
use Illuminate\Auth\Events\Login;
use Illuminate\Auth\Events\Logout;
use Illuminate\Cache\RateLimiting\Limit;
use Illuminate\Cookie\Middleware\EncryptCookies;
use Illuminate\Http\Request;
use Illuminate\Support\Carbon;
use Illuminate\Support\Facades\Event;
use Illuminate\Support\Facades\RateLimiter;
use Illuminate\Support\Facades\Route;
use Illuminate\Support\ServiceProvider;
use Illuminate\Validation\Rules\Password;
use Livewire\Livewire;
use Livewire\Mechanisms\HandleRequests\RequireLivewireHeaders;

class AppServiceProvider extends ServiceProvider
{
    public function register(): void
    {
        //
    }

    public function boot(): void
    {
        Password::defaults(fn () => Password::min(8)->mixedCase()->numbers()->symbols());

        // Client-side UI preferences only (never session/auth state), set via raw
        // document.cookie and read back server-side for the anti-flash class on first paint.
        EncryptCookies::except(['color_scheme', 'sidebar_collapsed']);

        // Livewire's temporary-file-upload endpoint is registered globally at boot, outside
        // any page route's middleware. Its default is 'throttle:60,1' with no auth. The
        // Knowledge base screen uses WithFileUploads, so this endpoint needs auth.
        config(['livewire.temporary_file_upload.middleware' => ['auth', 'throttle:60,1']]);

        // Every wire:click/wire:submit action goes through one shared endpoint that Livewire
        // registers with no rate limit. Re-register it with throttle:mutations so every admin
        // action is covered app-wide in one place.
        Livewire::setUpdateRoute(fn ($handle, $path) => Route::post($path, $handle)
            ->middleware(['web', RequireLivewireHeaders::class, 'throttle:mutations']));

        $this->configureRateLimiters();
        $this->configureActivityLogging();

        // Store UTC, render IST (Asia/Kolkata) — CLAUDE.md's formatting convention.
        Carbon::macro('ist', function () {
            /** @var Carbon $this */
            return $this->clone()->setTimezone('Asia/Kolkata');
        });
    }

    private function configureRateLimiters(): void
    {
        // Keyed by email+IP (targeted) AND IP alone (broad), whichever hits first.
        RateLimiter::for('login', function (Request $request) {
            return [
                Limit::perMinute(5)->by($request->input('email').'|'.$request->ip()),
                Limit::perMinute(10)->by($request->ip()),
            ];
        });

        RateLimiter::for('two-factor', function (Request $request) {
            return Limit::perMinute(5)
                ->by($request->session()->get('login.id').'|'.$request->ip());
        });

        RateLimiter::for('password-reset', function (Request $request) {
            return Limit::perMinute(5)->by($request->input('email').'|'.$request->ip());
        });

        RateLimiter::for('mutations', function (Request $request) {
            return Limit::perMinute(60)->by($request->user()?->id ?: $request->ip());
        });

        RateLimiter::for('ask', function (Request $request) {
            return Limit::perMinute(10)->by($request->user()?->id ?: $request->ip());
        });

        RateLimiter::for('chat', function (Request $request) {
            return Limit::perMinute(10)->by($request->user()?->id ?: $request->ip());
        });
    }

    private function configureActivityLogging(): void
    {
        Event::listen(Login::class, function (Login $event) {
            ActivityLog::record('auth.login', request(), ['guard' => $event->guard]);
        });

        // Fired inside Auth::logout() after the guard has cleared the user, so auth()->id()
        // is null by now — $event->user carries the actor instead.
        Event::listen(Logout::class, function (Logout $event) {
            if ($event->user) {
                ActivityLog::record('auth.logout', request(), [], $event->user->id);
            }
        });
    }
}
