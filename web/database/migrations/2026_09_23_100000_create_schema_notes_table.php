<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::create('schema_notes', function (Blueprint $table) {
            $table->id();
            $table->string('table_name');
            // '' means the note is about the table itself, not one column — kept as an
            // empty string rather than null so the unique constraint below actually holds
            // (MySQL treats every null as distinct, so a nullable column_name would let
            // more than one table-level note in).
            $table->string('column_name')->default('');
            $table->text('note');
            $table->timestamps();

            $table->unique(['table_name', 'column_name']);
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('schema_notes');
    }
};
