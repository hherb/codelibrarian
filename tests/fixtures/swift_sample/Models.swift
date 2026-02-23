import Foundation
import UIKit

/// A base class for all animals
class Animal {
    var name: String
    var age: Int

    init(name: String, age: Int) {
        self.name = name
        self.age = age
    }

    /// Return the sound this animal makes
    func speak() -> String {
        return ""
    }
}

class Dog: Animal {
    var breed: String

    init(name: String, age: Int, breed: String = "unknown") {
        self.breed = breed
        super.init(name: name, age: age)
    }

    override func speak() -> String {
        return "Woof!"
    }

    func fetch(item: String) -> String {
        return "\(name) fetched \(item)"
    }
}

protocol Greetable {
    func greet(name: String) -> String
}

struct Greeting: Greetable {
    let prefix: String

    func greet(name: String) -> String {
        return "\(prefix) \(name)"
    }
}

enum Color: String, CaseIterable {
    case red
    case green
    case blue
}

func findOldest(animals: [Animal]) -> Animal? {
    return animals.max(by: { $0.age < $1.age })
}

extension Dog: Greetable {
    func greet(name: String) -> String {
        return "Woof \(name)"
    }
}
