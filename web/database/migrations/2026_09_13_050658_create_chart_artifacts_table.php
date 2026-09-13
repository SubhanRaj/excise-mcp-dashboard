<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    /**
     * Run the migrations.
     */
    public function up(): void
    {
        Schema::create('chart_artifacts', function (Blueprint $table) {
            $table->ulid('id')->primary();
            // Polymorphic: a queries row or a message_tool_calls row (Phase 3) can each
            // produce one chart — one export/render code path either way
            // (web/plan/webui.md §7).
            $table->string('owner_type');
            $table->ulid('owner_id');
            $table->json('spec')->nullable();
            $table->string('png_path')->nullable();
            $table->string('svg_path')->nullable();
            $table->string('pdf_path')->nullable();
            $table->timestamps();
            $table->softDeletes();

            $table->index(['owner_type', 'owner_id']);
        });
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        Schema::dropIfExists('chart_artifacts');
    }
};
