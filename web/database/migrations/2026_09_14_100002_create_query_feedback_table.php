<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::create('query_feedback', function (Blueprint $table) {
            $table->ulid('id')->primary();
            $table->foreignUlid('query_id')->constrained('queries')->cascadeOnDelete();
            $table->foreignId('user_id')->constrained()->cascadeOnDelete();
            $table->boolean('thumbs_up');
            $table->text('note')->nullable();
            $table->timestamps();

            // One feedback row per person per query — resubmitting updates it.
            $table->unique(['query_id', 'user_id']);
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('query_feedback');
    }
};
