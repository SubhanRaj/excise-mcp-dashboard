<?php

namespace Tests\Feature\Admin;

use App\Http\Middleware\IsAdmin;
use Tests\TestCase;

/**
 * Pulse and Telescope are both disabled in the test environment (phpunit.xml
 * sets PULSE_ENABLED/TELESCOPE_ENABLED=false, the standard Laravel setup —
 * recording every test request would be wasteful), so their routes don't
 * exist here to hit over HTTP. What's tested instead is the actual guard
 * config, since both packages ship a default authorization that grants
 * access to anyone when app()->environment('local') — true on this box,
 * which is also genuinely public through the Cloudflare Tunnel. Verified
 * live (an authenticated non-admin gets 403, an admin gets 200) rather than
 * here, where the dashboards can't run at all.
 */
class MonitoringDashboardsTest extends TestCase
{
    public function test_pulse_requires_admin(): void
    {
        $this->assertContains(IsAdmin::class, config('pulse.middleware'));
        $this->assertContains('auth', config('pulse.middleware'));
    }

    public function test_telescope_requires_admin(): void
    {
        $this->assertContains(IsAdmin::class, config('telescope.middleware'));
        $this->assertContains('auth', config('telescope.middleware'));
    }
}
