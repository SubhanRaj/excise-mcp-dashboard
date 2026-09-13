<?php

namespace App\Providers;

use Illuminate\Support\ServiceProvider;
use Laravel\Fortify\Fortify;

class FortifyServiceProvider extends ServiceProvider
{
    public function register(): void
    {
        // Fortify stays installed only for password-validation rules and the
        // 'two-factor' rate-limiter name — auth itself is a fully custom
        // email+password+OTP flow (see CLAUDE.md).
        //
        // Must run in register(), not boot(): all providers' register() calls run
        // before any provider's boot() call, and the vendor Fortify provider — which
        // reads this flag inside its own boot() to decide whether to register
        // /register, /reset-password, /passkeys/*, and two-factor routes — is
        // auto-discovered and boots before this app provider. Calling ignoreRoutes()
        // from boot() would be too late.
        Fortify::ignoreRoutes();
    }
}
