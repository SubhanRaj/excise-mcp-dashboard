<?php

namespace Tests\Feature;

use App\Livewire\Chat;
use App\Models\ChartArtifact;
use App\Models\Conversation;
use App\Models\Message;
use App\Models\MessageToolCall;
use App\Models\User;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\Http;
use Livewire\Livewire;
use Tests\TestCase;

class ChatTest extends TestCase
{
    use RefreshDatabase;

    public function test_sending_a_first_message_creates_a_conversation_and_dispatches_the_send_event(): void
    {
        $user = User::factory()->create();

        // Chat::send() only creates the conversation row and hands off to the browser's
        // fetch() (via the dispatched event) — ChatController::send() is what persists the
        // user/assistant messages, covered separately below.
        Livewire::actingAs($user)->test(Chat::class)
            ->set('message', 'How many districts are in each zone?')
            ->call('send')
            ->assertDispatched(
                'chat-message-ready',
                message: 'How many districts are in each zone?',
            );

        $this->assertDatabaseHas('conversations', ['user_id' => $user->id]);
    }

    public function test_a_blank_message_is_rejected(): void
    {
        $user = User::factory()->create();

        Livewire::actingAs($user)->test(Chat::class)
            ->set('message', '')
            ->call('send')
            ->assertHasErrors('message');
    }

    public function test_the_stream_persists_assistant_tokens_and_a_tool_call_with_its_chart(): void
    {
        $user = User::factory()->create();
        $conversation = Conversation::create(['user_id' => $user->id]);

        Http::fake([
            '*/chat' => Http::response(
                $this->ndjson([
                    ['token' => 'Here '],
                    ['token' => 'is the trend.'],
                    ['tool_call' => ['name' => 'make_chart', 'arguments' => ['spec' => 'x', 'data_ref' => $conversation->id]]],
                    ['tool_result' => ['name' => 'make_chart', 'ok' => true, 'summary' => 'Chart rendered.']],
                    ['chart' => ['plotly_json' => json_encode(['data' => [], 'layout' => []])]],
                    ['done' => ['tool_calls_count' => 1]],
                ]),
                200,
            ),
        ]);

        $response = $this->actingAs($user)->post(route('chat.send', $conversation), [
            'message' => 'Chart the Lucknow revenue trend.',
        ]);
        $response->streamedContent();

        $this->assertDatabaseHas('messages', ['role' => 'user', 'content' => 'Chart the Lucknow revenue trend.']);

        $assistant = Message::where('conversation_id', $conversation->id)->where('role', 'assistant')->first();
        $this->assertNotNull($assistant);
        $this->assertSame('Here is the trend.', $assistant->content);

        $toolCall = MessageToolCall::where('message_id', $assistant->id)->first();
        $this->assertNotNull($toolCall);
        $this->assertSame('make_chart', $toolCall->tool_name);
        $this->assertTrue($toolCall->result_summary['ok']);

        $this->assertDatabaseHas('chart_artifacts', [
            'owner_type' => MessageToolCall::class,
            'owner_id' => $toolCall->id,
        ]);
        $this->assertNotNull(ChartArtifact::where('owner_id', $toolCall->id)->first()->spec);
    }

    public function test_an_unknown_model_key_is_refused(): void
    {
        $user = User::factory()->create();
        $conversation = Conversation::create(['user_id' => $user->id]);

        $this->actingAs($user)
            ->post(route('chat.send', $conversation), ['message' => 'hi', 'model' => 'not-a-real-model'])
            ->assertStatus(422);
    }

    public function test_a_user_cannot_send_to_another_users_conversation(): void
    {
        $owner = User::factory()->create();
        $other = User::factory()->create();
        $conversation = Conversation::create(['user_id' => $owner->id]);

        $this->actingAs($other)
            ->post(route('chat.send', $conversation), ['message' => 'hi'])
            ->assertForbidden();
    }

    public function test_reopening_a_conversation_resumes_its_persisted_history(): void
    {
        $user = User::factory()->create();
        $conversation = Conversation::create(['user_id' => $user->id, 'title' => 'Past conversation']);
        $conversation->messages()->create(['role' => 'user', 'content' => 'Earlier question']);
        $conversation->messages()->create(['role' => 'assistant', 'content' => 'Earlier answer']);

        Livewire::actingAs($user)->test(Chat::class, ['conversation' => $conversation])
            ->assertSee('Earlier question')
            ->assertSee('Past conversation');
    }

    /**
     * @param  list<array<string, mixed>>  $events
     */
    private function ndjson(array $events): string
    {
        return implode("\n", array_map(fn (array $e) => json_encode($e), $events))."\n";
    }
}
