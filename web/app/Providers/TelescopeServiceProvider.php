<?php

namespace App\Providers;

use Laravel\Telescope\IncomingEntry;
use Laravel\Telescope\Telescope;
use Laravel\Telescope\TelescopeApplicationServiceProvider;

class TelescopeServiceProvider extends TelescopeApplicationServiceProvider
{
    public function register(): void
    {
        $this->hideSensitiveRequestDetails();

        Telescope::filter(fn (IncomingEntry $entry) => true);
    }

    /**
     * The published scaffold only redacts request/header fields when
     * app()->environment() isn't 'local' — this box runs as 'local' while
     * genuinely public through the Cloudflare Tunnel, so that branch would
     * leave everything unredacted. Applied unconditionally instead.
     */
    protected function hideSensitiveRequestDetails(): void
    {
        Telescope::hideRequestParameters([
            '_token', 'password', 'password_confirmation', 'otp', 'code',
        ]);

        Telescope::hideRequestHeaders([
            'cookie', 'x-csrf-token', 'x-xsrf-token', 'authorization',
        ]);
    }

    /**
     * The published scaffold's authorization() (TelescopeApplicationServiceProvider,
     * vendor/laravel/telescope) grants access to anyone at all when
     * app()->environment('local') — true on this box, which is also genuinely
     * public through the tunnel. Overridden entirely rather than just gate(),
     * since gate() alone never overrides that env-based bypass.
     */
    protected function authorization(): void
    {
        Telescope::auth(fn ($request) => $request->user()?->isAdmin() ?? false);
    }
}
