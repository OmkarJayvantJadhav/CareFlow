# C

## Where it fits in my work (say this honestly)
C is **not used in CareFlow or MedVision**. I learned it in my B.Tech coursework and use it for data-structures and algorithms practice. It still matters to my AI work: NumPy, ONNX Runtime, LightGBM and PostgreSQL itself are written in C/C++, and knowing how memory and pointers work explains why vectorised NumPy is fast and why Python's GIL is released inside those libraries.

> If asked "where did you use C?" → "In coursework and DSA practice — for example implementing linked lists, stacks, sorting and file handling. My projects are in Python because of the AI ecosystem, but the heavy lifting inside the libraries I use is C/C++."

---

## 30-second answer
C is a compiled, statically typed, procedural language that gives direct control over memory through pointers. There is no garbage collector — you allocate with `malloc` and free with `free`. It is used for operating systems, embedded systems, databases and the native cores of high-performance libraries.

---

## Basics you must know

### Program structure
```c
#include <stdio.h>

int main(void) {
    printf("Hello\n");
    return 0;
}
```
Compile and run: `gcc main.c -o main && ./main`.

### Types and sizes (typical 64-bit)
`char` 1 byte, `int` 4, `long` 8, `float` 4, `double` 8, pointers 8. Use `sizeof`.

### Pointers
```c
int x = 10;
int *p = &x;   // p holds the address of x
*p = 20;       // dereference: x is now 20
```
- Arrays decay to pointers: `arr[i]` is `*(arr + i)`.
- Pass by pointer to modify a caller's variable: `void swap(int *a, int *b)`.
- `NULL` pointer, dangling pointer (points to freed memory), wild pointer (uninitialised).

### Memory
| Area | What lives there |
|---|---|
| Stack | Local variables, function frames — freed automatically |
| Heap | `malloc` / `calloc` / `realloc` — you must `free` |
| Data/BSS | Globals and `static` variables |

Common bugs: memory leak (forgot `free`), double free, buffer overflow, use-after-free.

### Strings
Character arrays ending in `'\0'`. `strlen`, `strcpy` (unsafe), `strncpy`, `strcmp`, `strcat`.

### Structs
```c
typedef struct Node {
    int value;
    struct Node *next;
} Node;
```

### Other keywords
`static` (keeps value between calls / file-private), `const`, `extern`, `volatile`, preprocessor `#define`, `#include`, header guards.

### File I/O
`fopen`, `fprintf`, `fscanf`, `fgets`, `fclose`.

---

## Link to my AI work (good talking points)
- **Why NumPy is fast:** a NumPy array is a contiguous C buffer; a vectorised operation runs one C loop instead of millions of Python bytecode steps. MedVision's quality gate computes a Laplacian over a whole image with array slicing (`gray[:-2, 1:-1] + gray[2:, 1:-1] + ...`) for this reason.
- **Memory layout:** row-major (C order) arrays are why `reshape` can be free and why feature maps shaped `(7, 7, 1280)` can be multiplied by a weight matrix with one `np.tensordot`.
- **PostgreSQL** (CareFlow's database) and the **pgvector** extension are written in C.

---

## Interview questions

**Q: Difference between `malloc` and `calloc`?**
`malloc(n)` allocates n bytes uninitialised; `calloc(count, size)` allocates and zero-fills.

**Q: What is a segmentation fault?**
Accessing memory the process is not allowed to (NULL dereference, out-of-bounds, freed memory).

**Q: Pass by value vs pass by reference in C?**
C is always pass by value; you simulate pass-by-reference by passing a pointer.

**Q: Stack vs heap?**
Stack: automatic, fast, limited size, freed when the function returns. Heap: manual, large, lives until `free`.

**Q: What does `static` mean inside a function?**
The variable keeps its value between calls and lives for the whole program.

**Q: Reverse a linked list.**
```c
Node *reverse(Node *head) {
    Node *prev = NULL;
    while (head) { Node *next = head->next; head->next = prev; prev = head; head = next; }
    return prev;
}
```
