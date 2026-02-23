package com.example.models

import java.util.UUID
import kotlinx.serialization.Serializable

/**
 * Base class for all animals
 */
open class Animal(
    val name: String,
    val age: Int
) {
    /** Return the sound this animal makes */
    open fun speak(): String {
        return ""
    }

    fun describe(): String {
        return "$name is $age years old"
    }
}

class Dog(
    name: String,
    age: Int,
    val breed: String = "unknown"
) : Animal(name, age) {

    override fun speak(): String {
        return "Woof!"
    }

    fun fetch(item: String): String {
        return "$name fetched $item"
    }
}

interface Greetable {
    fun greet(name: String): String
}

data class PetRecord(
    val id: Int,
    val animal: Animal,
    val owner: String? = null
) {
    fun isAdopted(): Boolean {
        return owner != null
    }
}

sealed class Result<out T> {
    data class Success<T>(val data: T) : Result<T>()
    data class Error(val message: String) : Result<Nothing>()
}

object PetRegistry {
    fun register(animal: Animal): Unit {
        println("Registered ${animal.name}")
    }
}

fun findOldest(animals: List<Animal>): Animal? {
    return animals.maxByOrNull { it.age }
}

suspend fun fetchAnimals(url: String): List<Animal> {
    return emptyList()
}

enum class Color(val hex: String) {
    RED("#FF0000"),
    GREEN("#00FF00"),
    BLUE("#0000FF");

    fun displayName(): String = name.lowercase()
}
