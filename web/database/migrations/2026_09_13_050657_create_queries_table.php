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
        Schema::create('queries', function (Blueprint $table) {
            $table->ulid('id')->primary();
            $table->foreignId('user_id')->constrained()->cascadeOnDelete();
            $table->string('request_id')->nullable();
            $table->text('prompt');
            $table->text('sql')->nullable();
            $table->string('engine')->nullable();
            $table->string('model')->nullable();
            $table->json('tables_used')->nullable();
            $table->unsignedInteger('row_count')->nullable();
            $table->json('timings')->nullable();
            // pending -> running -> complete | failed. current_stage carries the
            // orchestrator's finer-grained Stage.name (plan_sql, guard_sql, run_sql,
            // plan_plot, render, summarize) for the stage indicator.
            $table->string('status')->default('pending');
            $table->string('current_stage')->nullable();
            $table->json('rows_preview')->nullable();
            $table->text('summary')->nullable();
            $table->text('error_message')->nullable();
            $table->timestamps();
            $table->softDeletes();
        });
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        Schema::dropIfExists('queries');
    }
};
