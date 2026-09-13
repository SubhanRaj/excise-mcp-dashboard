<?php

namespace Tests\Feature\Admin;

use App\Livewire\Admin\GoogleConnectionIndex;
use App\Models\GoogleConnection;
use App\Models\User;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Livewire\Livewire;
use Tests\TestCase;

class GoogleConnectionTest extends TestCase
{
    use RefreshDatabase;

    public function test_a_non_privileged_user_is_forbidden(): void
    {
        $analyst = User::factory()->create(['role' => 'Analyst', 'privileges' => []]);

        $this->actingAs($analyst)->get(route('admin.google.index'))->assertForbidden();
    }

    public function test_the_connect_redirect_carries_the_google_drive_sheets_docs_scopes(): void
    {
        $admin = User::factory()->create(['role' => 'Admin']);
        config(['services.google.client_id' => 'test-client-id', 'services.google.client_secret' => 'test-secret', 'services.google.redirect' => 'https://example.test/google/callback']);

        $response = $this->actingAs($admin)->get(route('google.connect'));

        $response->assertRedirect();
        $location = $response->headers->get('Location');
        $this->assertStringContainsString('drive.readonly', $location);
        $this->assertStringContainsString('spreadsheets.readonly', $location);
        $this->assertStringContainsString('documents.readonly', $location);
        $this->assertStringContainsString('access_type=offline', $location);
        $this->assertStringContainsString('prompt=consent', $location);
    }

    public function test_disconnecting_deletes_the_connection_and_never_exposes_the_refresh_token(): void
    {
        $admin = User::factory()->create(['role' => 'Admin']);
        $connection = GoogleConnection::create([
            'user_id' => $admin->id,
            'google_sub' => '12345',
            'email' => 'admin@example.com',
            'scopes' => ['https://www.googleapis.com/auth/drive.readonly'],
            'refresh_token' => 'super-secret-refresh-token',
        ]);

        $response = Livewire::actingAs($admin)->test(GoogleConnectionIndex::class)
            ->call('disconnect', $connection->id);

        $response->assertDontSee('super-secret-refresh-token');
        $this->assertSoftDeleted('google_connections', ['id' => $connection->id]);
    }

    public function test_a_revoked_connection_shows_reconnect_needed(): void
    {
        $admin = User::factory()->create(['role' => 'Admin']);
        GoogleConnection::create([
            'user_id' => $admin->id, 'google_sub' => '1', 'email' => 'a@example.com',
            'refresh_token' => 'x', 'revoked_at' => now(),
        ]);

        Livewire::actingAs($admin)->test(GoogleConnectionIndex::class)
            ->assertSee('Reconnect needed');
    }
}
