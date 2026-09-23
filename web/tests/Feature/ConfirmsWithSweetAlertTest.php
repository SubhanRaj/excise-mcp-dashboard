<?php

namespace Tests\Feature;

use App\Livewire\Chat;
use App\Livewire\Concerns\ConfirmsWithSweetAlert;
use App\Models\Conversation;
use App\Models\User;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Livewire\Livewire;
use Tests\TestCase;

/**
 * App\Livewire\Concerns\ConfirmsWithSweetAlert, exercised through Chat's own
 * forceDeleteConversation — the trait replaces wire:confirm's native browser dialog
 * with SweetAlert2 (php-flasher/flasher-sweetalert-laravel), across every component
 * that uses it (Chat, Ask, KnowledgeBaseIndex, GoogleConnectionIndex, UserIndex).
 */
class ConfirmsWithSweetAlertTest extends TestCase
{
    use RefreshDatabase;

    public function test_confirming_runs_the_target_method_with_its_argument(): void
    {
        $user = User::factory()->create();
        $conversation = Conversation::create(['user_id' => $user->id]);

        // The exact shape flasher-sweetalert's JS dispatches to Livewire — traced from the
        // installed package's own source (flasher-sweetalert's renderEnvelope() and
        // flasher-sweetalert-laravel's LivewireListener), not assumed from the docs: the
        // browser-side confirm click fires window 'flasher:sweetalert:promise' with
        // { envelope, promise }, and LivewireListener.php relays it to the component that
        // created the envelope as `sweetalert:confirmed` with { payload: { envelope, promise } }.
        Livewire::actingAs($user)->test(Chat::class)
            ->call('runConfirmedAction', [
                'envelope' => [
                    'options' => ['method' => 'forceDeleteConversation', 'arg' => $conversation->id],
                ],
                'promise' => ['isConfirmed' => true],
            ]);

        // forceDeleteConversation is a real, permanent delete — not a soft one.
        $this->assertDatabaseMissing('conversations', ['id' => $conversation->id]);
    }

    public function test_an_unknown_method_in_the_payload_is_ignored(): void
    {
        $user = User::factory()->create();

        // No exception, no effect — a stale or tampered payload naming a method that
        // doesn't exist on the component must not raise, since it reaches this handler
        // as a plain browser event, not a validated server-trusted call.
        Livewire::actingAs($user)->test(Chat::class)
            ->call('runConfirmedAction', [
                'envelope' => ['options' => ['method' => 'notARealMethod', 'arg' => 'x']],
                'promise' => ['isConfirmed' => true],
            ])
            ->assertOk();
    }

    public function test_confirm_queues_a_sweetalert_envelope_carrying_the_target_method(): void
    {
        // Deliberately not through Livewire::test(): flasher-laravel's own bridge only fires
        // on a real X-Livewire request header (LivewireManager::isLivewireRequest()), which
        // the Livewire test harness's in-process ->call() never sets, so nothing would ever
        // reach app('flasher') that way. confirm() itself has no Livewire-specific state — a
        // plain object using the trait exercises the one thing actually worth verifying here:
        // that it calls the real sweetalert() API correctly and the options survive.
        $target = new class
        {
            use ConfirmsWithSweetAlert;
        };

        $target->confirm('forceDeleteConversation', 'conv-123', 'Sure?');

        $envelopes = app('flasher')->render('array', [])['envelopes'];
        $this->assertNotEmpty($envelopes);
        $options = $envelopes[0]['options'];
        $this->assertSame('forceDeleteConversation', $options['method']);
        $this->assertSame('conv-123', $options['arg']);
    }
}
