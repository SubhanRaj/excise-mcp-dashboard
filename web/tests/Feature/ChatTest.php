<?php

namespace Tests\Feature;

use App\Livewire\Chat;
use App\Models\ChartArtifact;
use App\Models\Conversation;
use App\Models\Message;
use App\Models\MessageToolCall;
use App\Models\User;
use App\Services\OrchestratorStream;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\Http;
use Livewire\Livewire;
use Tests\Support\FakeOrchestratorStream;
use Tests\Support\FlakyOrchestratorStream;
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

    public function test_clicking_an_example_question_fills_the_composer(): void
    {
        $user = User::factory()->create();
        $example = Chat::EXAMPLE_QUESTIONS[1];

        Livewire::actingAs($user)->test(Chat::class)
            ->call('useExample', $example['question'], $example['chart'])
            ->assertSet('message', $example['question'])
            ->assertSet('includeChart', $example['chart']);
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

        $this->app->instance(OrchestratorStream::class, new FakeOrchestratorStream([
            ['token' => 'Here '],
            ['token' => 'is the trend.'],
            ['tool_call' => ['name' => 'make_chart', 'arguments' => ['spec' => 'x']]],
            ['tool_result' => ['name' => 'make_chart', 'ok' => true, 'summary' => 'Chart rendered.']],
            ['chart' => ['plotly_json' => json_encode(['data' => [], 'layout' => []])]],
            ['done' => ['tool_calls_count' => 1, 'prompt_tokens' => 200, 'completion_tokens' => 50]],
        ]));

        $response = $this->actingAs($user)->post(route('chat.send', $conversation), [
            'message' => 'Chart the Lucknow revenue trend.',
        ]);
        $response->streamedContent();

        $this->assertDatabaseHas('messages', ['role' => 'user', 'content' => 'Chart the Lucknow revenue trend.']);

        $assistant = Message::where('conversation_id', $conversation->id)->where('role', 'assistant')->first();
        $this->assertNotNull($assistant);
        $this->assertSame('Here is the trend.', $assistant->content);
        $this->assertSame(200, $assistant->prompt_tokens);
        $this->assertSame(50, $assistant->completion_tokens);

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

    public function test_the_chart_toggle_hints_the_orchestrator_without_altering_the_stored_message(): void
    {
        // make_chart is the model's own judgment call ("only when a chart would help") and
        // correctly skips a single-number answer — the composer's toggle turns that judgment
        // into an explicit ask for one turn, without putting the instruction in the message
        // the user actually typed and sees in the transcript.
        $user = User::factory()->create();
        $conversation = Conversation::create(['user_id' => $user->id]);

        $fake = new FakeOrchestratorStream([
            ['token' => 'Here it is.'],
            ['done' => ['tool_calls_count' => 0, 'prompt_tokens' => 10, 'completion_tokens' => 5]],
        ]);
        $this->app->instance(OrchestratorStream::class, $fake);

        $this->actingAs($user)->post(route('chat.send', $conversation), [
            'message' => 'How many CL5C shops in Lucknow in August 2026?',
            'includeChart' => true,
        ])->streamedContent();

        $this->assertDatabaseHas('messages', [
            'role' => 'user',
            'content' => 'How many CL5C shops in Lucknow in August 2026?',
        ]);

        $this->assertStringContainsString(
            'Please include a chart to visualize the answer.',
            $fake->capturedPayload['message'] ?? '',
        );
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

    public function test_deleting_a_conversation_soft_deletes_it(): void
    {
        $user = User::factory()->create();
        $conversation = Conversation::create(['user_id' => $user->id]);

        Livewire::actingAs($user)->test(Chat::class)
            ->call('deleteConversation', $conversation->id);

        $this->assertSoftDeleted('conversations', ['id' => $conversation->id]);
    }

    public function test_a_user_cannot_delete_another_users_conversation(): void
    {
        $owner = User::factory()->create();
        $other = User::factory()->create();
        $conversation = Conversation::create(['user_id' => $owner->id]);

        Livewire::actingAs($other)->test(Chat::class)
            ->call('deleteConversation', $conversation->id)
            ->assertForbidden();
    }

    public function test_a_dropped_connection_can_be_resumed_and_the_replay_becomes_the_final_message(): void
    {
        // Cloudflare's own ~100s cap on total connection duration can end a stream
        // outright while the turn is still genuinely working (MCP_ENGINES.md §Streamed
        // events, confirmed live on a compound question) — the resume route reattaches
        // to the same turn_id and its full replay becomes the message's real content.
        $user = User::factory()->create();
        $conversation = Conversation::create(['user_id' => $user->id]);

        $fake = new FlakyOrchestratorStream(
            firstEvents: [['token' => 'Composite: ']],
            resumeEvents: [
                ['token' => 'Composite: 417, Country Liquor: 589, Total: 1006'],
                ['done' => ['tool_calls_count' => 1, 'prompt_tokens' => 300, 'completion_tokens' => 60]],
            ],
        );
        $this->app->instance(OrchestratorStream::class, $fake);

        $this->actingAs($user)->post(route('chat.send', $conversation), [
            'message' => 'How many country liquor and composite shops are in Lucknow in August 2026?',
        ])->streamedContent();

        $assistant = Message::where('conversation_id', $conversation->id)->where('role', 'assistant')->first();
        $this->assertNotNull($assistant);
        $this->assertSame('Composite: ', $assistant->content);

        $this->actingAs($user)
            ->post(route('chat.resume', [$conversation, $assistant]))
            ->streamedContent();

        $assistant->refresh();
        $this->assertSame('Composite: 417, Country Liquor: 589, Total: 1006', $assistant->content);
        $this->assertCount(2, $fake->capturedPayloads);
        $this->assertSame($assistant->id, $fake->capturedPayloads[1]['turn_id']);
    }

    public function test_resuming_clears_previously_persisted_tool_calls_before_replaying(): void
    {
        $user = User::factory()->create();
        $conversation = Conversation::create(['user_id' => $user->id]);

        $fake = new FlakyOrchestratorStream(
            firstEvents: [
                ['tool_call' => ['name' => 'run_sql_query', 'arguments' => ['question' => 'x']]],
                ['tool_result' => ['name' => 'run_sql_query', 'ok' => true, 'summary' => '3 rows']],
            ],
            resumeEvents: [
                ['tool_call' => ['name' => 'run_sql_query', 'arguments' => ['question' => 'x']]],
                ['tool_result' => ['name' => 'run_sql_query', 'ok' => true, 'summary' => '3 rows']],
                ['token' => 'Done.'],
                ['done' => ['tool_calls_count' => 1, 'prompt_tokens' => 100, 'completion_tokens' => 20]],
            ],
        );
        $this->app->instance(OrchestratorStream::class, $fake);

        $this->actingAs($user)->post(route('chat.send', $conversation), ['message' => 'x'])->streamedContent();
        $assistant = Message::where('conversation_id', $conversation->id)->where('role', 'assistant')->first();
        $this->assertSame(1, MessageToolCall::where('message_id', $assistant->id)->count());

        $this->actingAs($user)->post(route('chat.resume', [$conversation, $assistant]))->streamedContent();

        $this->assertSame(1, MessageToolCall::where('message_id', $assistant->id)->count());
    }

    public function test_a_resume_that_fails_immediately_does_not_erase_a_previously_saved_answer(): void
    {
        // A resume's own connection can drop again before replaying anything — confirmed
        // live, a make_chart retry made a turn run long enough to need a second resume,
        // and that second attempt died with zero events, which used to overwrite the
        // real, already-saved answer with empty content (persistIfNotWorseThanBefore()
        // above is what stops it).
        $user = User::factory()->create();
        $conversation = Conversation::create(['user_id' => $user->id]);

        $fake = new FlakyOrchestratorStream(
            firstEvents: [
                ['tool_call' => ['name' => 'run_sql_query', 'arguments' => ['question' => 'x']]],
                ['tool_result' => ['name' => 'run_sql_query', 'ok' => true, 'summary' => '3 rows']],
                ['token' => 'The total beer revenue was Rs 7,142.87 crore.'],
                ['done' => ['tool_calls_count' => 1, 'prompt_tokens' => 200, 'completion_tokens' => 50]],
            ],
            resumeEvents: [],
            firstCallSucceeds: true,
        );
        $this->app->instance(OrchestratorStream::class, $fake);

        $this->actingAs($user)->post(route('chat.send', $conversation), ['message' => 'x'])->streamedContent();
        $assistant = Message::where('conversation_id', $conversation->id)->where('role', 'assistant')->first();
        $this->assertSame('The total beer revenue was Rs 7,142.87 crore.', $assistant->content);
        $this->assertSame(1, MessageToolCall::where('message_id', $assistant->id)->count());

        $this->actingAs($user)->post(route('chat.resume', [$conversation, $assistant]))->streamedContent();

        $assistant->refresh();
        $this->assertSame('The total beer revenue was Rs 7,142.87 crore.', $assistant->content);
        $this->assertSame(1, MessageToolCall::where('message_id', $assistant->id)->count());
    }

    public function test_a_user_cannot_resume_another_users_conversation(): void
    {
        $owner = User::factory()->create();
        $other = User::factory()->create();
        $conversation = Conversation::create(['user_id' => $owner->id]);
        $message = $conversation->messages()->create(['role' => 'assistant', 'content' => '']);

        $this->actingAs($other)
            ->post(route('chat.resume', [$conversation, $message]))
            ->assertForbidden();
    }

    public function test_stopping_a_turn_cancels_it_on_the_orchestrator(): void
    {
        $user = User::factory()->create();
        $conversation = Conversation::create(['user_id' => $user->id]);
        $message = $conversation->messages()->create(['role' => 'assistant', 'content' => '']);

        Http::fake(['*/chat/turn/*/cancel' => Http::response(['cancelled' => true])]);

        $this->actingAs($user)
            ->post(route('chat.cancel', [$conversation, $message]))
            ->assertOk()
            ->assertJson(['cancelled' => true]);

        Http::assertSent(fn ($request) => str_contains($request->url(), "/chat/turn/{$message->id}/cancel"));
    }

    public function test_a_user_cannot_cancel_another_users_conversation(): void
    {
        $owner = User::factory()->create();
        $other = User::factory()->create();
        $conversation = Conversation::create(['user_id' => $owner->id]);
        $message = $conversation->messages()->create(['role' => 'assistant', 'content' => '']);

        $this->actingAs($other)
            ->post(route('chat.cancel', [$conversation, $message]))
            ->assertForbidden();
    }

    public function test_force_deleting_a_conversation_removes_it_and_its_chart_artifacts(): void
    {
        $user = User::factory()->create();
        $conversation = Conversation::create(['user_id' => $user->id]);
        $message = $conversation->messages()->create(['role' => 'assistant', 'content' => 'x']);
        $toolCall = $message->toolCalls()->create(['tool_name' => 'make_chart', 'arguments' => []]);
        ChartArtifact::create([
            'owner_type' => MessageToolCall::class,
            'owner_id' => $toolCall->id,
            'spec' => ['data' => [], 'layout' => []],
        ]);

        Livewire::actingAs($user)->test(Chat::class)
            ->call('forceDeleteConversation', $conversation->id);

        $this->assertDatabaseMissing('conversations', ['id' => $conversation->id]);
        $this->assertDatabaseMissing('messages', ['id' => $message->id]);
        $this->assertDatabaseMissing('chart_artifacts', ['owner_id' => $toolCall->id]);
    }
}
