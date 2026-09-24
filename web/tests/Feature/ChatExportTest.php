<?php

namespace Tests\Feature;

use App\Models\ChartArtifact;
use App\Models\Conversation;
use App\Models\Message;
use App\Models\MessageToolCall;
use App\Models\User;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\Http;
use Tests\TestCase;

class ChatExportTest extends TestCase
{
    use RefreshDatabase;

    public function test_the_owner_downloads_a_pdf_transcript(): void
    {
        $user = User::factory()->create();
        $conversation = Conversation::create(['user_id' => $user->id, 'title' => 'Lucknow revenue']);
        Message::create(['conversation_id' => $conversation->id, 'role' => 'user', 'content' => 'How much revenue?']);
        $assistant = Message::create([
            'conversation_id' => $conversation->id,
            'role' => 'assistant',
            'content' => 'Here is the figure.',
        ]);
        $toolCall = MessageToolCall::create([
            'message_id' => $assistant->id,
            'tool_name' => 'run_sql_query',
            'arguments' => ['question' => 'revenue'],
            'result_summary' => ['summary' => '1 row(s)'],
        ]);
        ChartArtifact::create([
            'owner_type' => MessageToolCall::class,
            'owner_id' => $toolCall->id,
            'spec' => ['data' => [], 'layout' => []],
        ]);

        Http::fake(['*/chart/render' => Http::response('fake-png-bytes', 200)]);

        $response = $this->actingAs($user)->get(route('chat.export', $conversation));

        $response->assertOk();
        $response->assertHeader('Content-Type', 'application/pdf');
    }

    public function test_another_users_conversation_is_forbidden(): void
    {
        $owner = User::factory()->create();
        $intruder = User::factory()->create();
        $conversation = Conversation::create(['user_id' => $owner->id]);

        $this->actingAs($intruder)
            ->get(route('chat.export', $conversation))
            ->assertForbidden();
    }
}
