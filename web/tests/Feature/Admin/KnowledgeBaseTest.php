<?php

namespace Tests\Feature\Admin;

use App\Livewire\Admin\KnowledgeBaseIndex;
use App\Models\KbUpload;
use App\Models\User;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Http\Testing\File;
use Illuminate\Support\Facades\Http;
use Illuminate\Support\Facades\Storage;
use Livewire\Livewire;
use Tests\TestCase;

class KnowledgeBaseTest extends TestCase
{
    use RefreshDatabase;

    protected function setUp(): void
    {
        parent::setUp();

        // No real orchestrator in the test environment — the corpus panel degrades to its
        // "unreachable" state rather than making a real network call.
        Http::fake(fn () => Http::response(null, 500));
    }

    public function test_a_non_privileged_user_is_forbidden(): void
    {
        $analyst = User::factory()->create(['role' => 'Analyst', 'privileges' => []]);

        $this->actingAs($analyst)->get(route('admin.knowledge.index'))->assertForbidden();
    }

    public function test_a_valid_markdown_file_is_accepted_and_creates_a_pending_upload(): void
    {
        Storage::fake('kb-uploads');
        $admin = User::factory()->create(['role' => 'Admin']);
        $file = File::create('policy-note.md', 10)->size(10);

        Livewire::actingAs($admin)->test(KnowledgeBaseIndex::class)
            ->set('title', 'Policy Note')
            ->set('file', $file)
            ->call('upload')
            ->assertHasNoErrors();

        $this->assertDatabaseHas('kb_uploads', [
            'title' => 'Policy Note',
            'status' => KbUpload::STATUS_PENDING,
            'uploaded_by' => $admin->id,
        ]);
    }

    public function test_a_non_markdown_file_is_rejected(): void
    {
        Storage::fake('kb-uploads');
        $admin = User::factory()->create(['role' => 'Admin']);
        $file = File::create('not-markdown.pdf', 10);

        Livewire::actingAs($admin)->test(KnowledgeBaseIndex::class)
            ->set('title', 'Bad File')
            ->set('file', $file)
            ->call('upload')
            ->assertHasErrors('file');

        $this->assertDatabaseMissing('kb_uploads', ['title' => 'Bad File']);
    }

    public function test_an_oversize_file_is_rejected(): void
    {
        Storage::fake('kb-uploads');
        $admin = User::factory()->create(['role' => 'Admin']);
        $file = File::create('huge.md', 3000); // KB, over the 2048 KB cap

        Livewire::actingAs($admin)->test(KnowledgeBaseIndex::class)
            ->set('title', 'Huge File')
            ->set('file', $file)
            ->call('upload')
            ->assertHasErrors('file');
    }

    public function test_the_stored_filename_never_uses_the_clients_original_name(): void
    {
        Storage::fake('kb-uploads');
        $admin = User::factory()->create(['role' => 'Admin']);
        $file = File::create('../../etc/passwd.md', 10);

        Livewire::actingAs($admin)->test(KnowledgeBaseIndex::class)
            ->set('title', 'Traversal Attempt')
            ->set('file', $file)
            ->call('upload');

        // Illuminate's test file fake already reduces the client name to its basename;
        // the real protection this asserts is that the stored path is Str::slug($title)
        // derived, never built from any part of the client-supplied filename.
        $upload = KbUpload::where('title', 'Traversal Attempt')->firstOrFail();
        $this->assertStringNotContainsString('..', $upload->origin_ref);
        $this->assertStringNotContainsString('passwd', $upload->origin_ref);
        $this->assertStringStartsWith('traversal-attempt-', $upload->origin_ref);
    }

    public function test_withdrawing_an_upload_marks_it_withdrawn(): void
    {
        $admin = User::factory()->create(['role' => 'Admin']);
        $upload = KbUpload::create([
            'uploaded_by' => $admin->id, 'original_name' => 'a.md', 'title' => 'A',
            'status' => KbUpload::STATUS_PENDING, 'origin_ref' => 'a-xxxx.md',
        ]);

        Livewire::actingAs($admin)->test(KnowledgeBaseIndex::class)
            ->call('withdraw', $upload->id);

        $this->assertSame(KbUpload::STATUS_WITHDRAWN, $upload->fresh()->status);
    }
}
