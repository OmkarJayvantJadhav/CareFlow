# C++

## Where it fits in my work (say this honestly)
C++ is **not used in CareFlow or MedVision**; I use it for **data structures and algorithms / competitive programming** and learned OOP with it in coursework. It is relevant to my AI stack because **TensorFlow, ONNX Runtime and LightGBM are written in C++** — my Python code calls into them.

> If asked "where did you use C++?" → "For DSA practice with the STL — vectors, maps, priority queues — and OOP coursework. My projects use Python, but the engines underneath (TensorFlow, ONNX Runtime, LightGBM) are C++, and that's why I export to ONNX: it runs the model in a C++ runtime without the TensorFlow Python stack."

---

## 30-second answer
C++ is C plus object-oriented programming, templates (generic programming) and a rich standard library (STL). It compiles to fast native code and gives control over memory, with RAII and smart pointers to manage it safely.

---

## Basics you must know

### OOP
```cpp
class Shape {
public:
    virtual double area() const = 0;   // pure virtual → abstract class
    virtual ~Shape() = default;        // virtual destructor for base classes
};

class Circle : public Shape {
    double r;
public:
    explicit Circle(double r) : r(r) {}
    double area() const override { return 3.14159 * r * r; }
};
```
- **Encapsulation** (private/protected/public), **inheritance**, **polymorphism** (virtual functions, vtable), **abstraction** (pure virtual).
- Overloading (compile time) vs overriding (run time).

### References vs pointers
`int &r = x;` — an alias, cannot be null or re-seated. Pointers can be null and re-pointed.

### Memory management
- `new` / `delete` (avoid raw).
- **RAII:** acquire a resource in a constructor, release it in the destructor.
- Smart pointers: `std::unique_ptr` (single owner), `std::shared_ptr` (reference counted), `std::weak_ptr` (breaks cycles).
- Rule of three / five: if you write a destructor, copy constructor or copy assignment, you probably need all (plus move versions).

### STL (most used in DSA)
| Container | Use | Complexity |
|---|---|---|
| `vector` | Dynamic array | O(1) index, amortised O(1) push_back |
| `deque` | Push/pop both ends | O(1) |
| `list` | Doubly linked list | O(1) insert with iterator |
| `map` / `set` | Ordered (red-black tree) | O(log n) |
| `unordered_map` / `unordered_set` | Hash table | O(1) average |
| `priority_queue` | Heap | O(log n) push/pop |
| `stack`, `queue` | Adapters | O(1) |

Algorithms: `sort`, `lower_bound`, `upper_bound`, `binary_search`, `reverse`, `accumulate`, `next_permutation`.

### Templates
```cpp
template <typename T>
T maxOf(T a, T b) { return a > b ? a : b; }
```

### Modern C++ (11/14/17)
`auto`, range-based `for`, lambdas `[&](int x){ return x * 2; }`, `move` semantics, `nullptr`, `constexpr`.

---

## Connection to my projects
- **ONNX Runtime** is a C++ inference engine. MedVision creates an `ort.InferenceSession` in Python, but the matrix multiplications run in C++ with graph optimisations (`ORT_ENABLE_ALL`). That is why the served model takes about 30 ms per image on a CPU.
- **LightGBM** (CareFlow wait-time model) is a C++ library; the trained boosters are saved as text files (`app/ml/artifacts/mid.txt`) and loaded with `lgb.Booster(model_file=...)`.
- CareFlow's queue merge logic and MedVision's group splitting use the same ideas as STL containers: priority ordering, union-find style connected components (`merge_groups` in `ml/src/medvision_ml/data/groups.py`).

---

## Interview questions

**Q: Virtual function and vtable?**
A virtual call is resolved at run time through a per-class table of function pointers, enabling polymorphism.

**Q: Why a virtual destructor?**
So deleting a derived object through a base pointer calls the derived destructor.

**Q: `map` vs `unordered_map`?**
`map` is ordered (tree, O(log n)); `unordered_map` is a hash table (O(1) average, no order).

**Q: What is RAII?**
Tie resource lifetime to an object's lifetime so destructors release it automatically — like Python's `with` statement.

**Q: Struct vs class?**
Only the default access: `struct` members are public by default, `class` members private.
