<?php

namespace Tests\Feature;

use Tests\TestCase;

class HealthCheckTest extends TestCase
{
    public function test_health_endpoint_returns_ok_and_the_app_name_without_auth(): void
    {
        $response = $this->getJson('/health');

        $response->assertOk();
        $response->assertJsonStructure(['app', 'status']);
        $response->assertJson([
            'app' => config('app.name'),
            'status' => 'ok',
        ]);
    }
}
