<?php

namespace Tests\Feature;

use App\Models\User;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\TestCase;

class UiPreferencesTest extends TestCase
{
    use RefreshDatabase;

    private array $validPrefs = [
        'theme' => 'dark',
        'font' => 'merriweather',
        'text_size' => 3,
        'line_spacing' => 'relaxed',
        'content_width' => 'wide',
        'table_density' => 'compact',
        'accent' => 'saffron',
        'high_contrast' => false,
        'reduce_motion' => true,
    ];

    public function test_a_pref_change_persists_to_the_signed_in_users_row(): void
    {
        $user = User::factory()->create();

        $this->actingAs($user)->patch(route('account.ui-prefs'), $this->validPrefs)->assertOk();

        $this->assertSame($this->validPrefs, $user->refresh()->ui_prefs);
    }

    public function test_an_invalid_value_is_rejected_and_nothing_is_saved(): void
    {
        $user = User::factory()->create();

        $this->actingAs($user)
            ->patch(route('account.ui-prefs'), array_merge($this->validPrefs, ['accent' => 'crimson']))
            ->assertInvalid(['accent']);

        $this->assertNull($user->refresh()->ui_prefs);
    }

    public function test_an_unauthenticated_request_is_redirected_to_login(): void
    {
        $this->patch(route('account.ui-prefs'), $this->validPrefs)->assertRedirect(route('login'));
    }
}
