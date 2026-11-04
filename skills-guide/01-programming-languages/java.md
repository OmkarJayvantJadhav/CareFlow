# Java

## Where it fits in my work (say this honestly)
Java is **not used in CareFlow or MedVision**. I learned it in coursework (OOP, collections, exceptions, JDBC-style database access). Many of the backend design ideas I used in Python — layered services, dependency injection, ORM entities, transactions — come from the Java/Spring world, so I can map them across.

> If asked "where did you use Java?" → "In coursework for OOP and DSA. In my projects I chose Python for the AI ecosystem, but the patterns map directly: FastAPI's `Depends` is like Spring dependency injection, SQLAlchemy is like Hibernate/JPA, and Pydantic models are like DTOs with Bean Validation."

---

## 30-second answer
Java is a statically typed, object-oriented language that compiles to bytecode and runs on the **JVM** ("write once, run anywhere"). It has automatic garbage collection, strong typing, a large standard library (Collections, concurrency) and is widely used for enterprise backends (Spring Boot) and Android.

---

## Basics you must know

### JDK, JRE, JVM
- **JVM** runs bytecode (with JIT compilation to native code).
- **JRE** = JVM + standard libraries.
- **JDK** = JRE + compiler (`javac`) and tools.

### OOP pillars
```java
interface Shape { double area(); }

abstract class Base implements Shape {
    protected final String name;
    Base(String name) { this.name = name; }
}

class Circle extends Base {
    private final double r;
    Circle(double r) { super("circle"); this.r = r; }
    @Override public double area() { return Math.PI * r * r; }
}
```
- Encapsulation, inheritance (single class inheritance, multiple interfaces), polymorphism, abstraction.
- `abstract class` vs `interface` (interfaces can have `default` methods since Java 8).
- `final` (constant / no override / no subclass), `static` (belongs to the class).

### Collections Framework
| Interface | Common classes |
|---|---|
| `List` | `ArrayList` (array), `LinkedList` |
| `Set` | `HashSet`, `LinkedHashSet`, `TreeSet` (sorted) |
| `Map` | `HashMap`, `LinkedHashMap`, `TreeMap` |
| `Queue` / `Deque` | `ArrayDeque`, `PriorityQueue` |

`equals()` and `hashCode()` must agree for objects used as keys.

### Exceptions
- **Checked** (must be declared/caught, e.g. `IOException`) vs **unchecked** (`RuntimeException`, e.g. `NullPointerException`).
- `try-with-resources` closes resources automatically (like Python's `with`).

### Strings
`String` is immutable; use `StringBuilder` for repeated concatenation. String pool and `==` vs `.equals()`.

### Java 8+ features
Lambdas, `Stream` API (`list.stream().filter(...).map(...).collect(...)`), `Optional`, `var` (Java 10), records (Java 16).

### Concurrency
`Thread`, `Runnable`, `ExecutorService`, `synchronized`, `volatile`, `ConcurrentHashMap`.

### Memory / GC
Heap (objects) and stack (frames); generational garbage collection.

---

## Mapping Java concepts to what I built

| Java / Spring idea | My Python equivalent | Where |
|---|---|---|
| Spring `@RestController` + `@GetMapping` | FastAPI `APIRouter` + `@router.get` | `app/api/routes.py`, `backend/app/api/v1/routes.py` |
| Dependency injection (`@Autowired`) | FastAPI `Depends(get_db)`, `Depends(get_auth)` | `app/api/deps.py` |
| JPA/Hibernate `@Entity` | SQLAlchemy `class Appointment(Base)` | `app/db/models.py` |
| `@Transactional` | `session_scope()` commit/rollback, `begin_nested()` savepoints | `app/db/session.py`, `app/agent/tools.py` |
| Flyway / Liquibase migrations | Alembic | `alembic/versions/` |
| DTO + Bean Validation (`@NotNull`, `@Size`) | Pydantic models with `Field(gt=0, max_length=60)` | `app/agent/tools.py` |
| `synchronized` | `threading.Lock` | `app/safety/emergency.py`, `app/ml/model.py` |
| `enum` | `StrEnum` | `backend/app/inference/decision.py` |

---

## Interview questions

**Q: Why is `String` immutable?**
Security, thread safety, caching in the string pool, and safe use as `HashMap` keys.

**Q: `HashMap` internals?**
Array of buckets; the key's `hashCode` picks a bucket; collisions are stored in a linked list that turns into a balanced tree when long (Java 8+). Average O(1).

**Q: `==` vs `.equals()`?**
`==` compares references; `.equals()` compares content.

**Q: Overloading vs overriding?**
Overloading: same name, different parameters, resolved at compile time. Overriding: subclass replaces a parent method, resolved at run time.

**Q: Checked vs unchecked exceptions?**
Checked must be handled or declared; unchecked (runtime) need not be.
