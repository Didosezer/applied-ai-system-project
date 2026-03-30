# PawPal+ Project Reflection

## 1. System Design

**a. Initial design**

- Briefly describe your initial UML design.

The design has four classes connected in a hierarchy: Owner contains Pets, and each Pet contains Tasks. Scheduler is a separate class that takes an Owner and queries through this hierarchy to return a filtered list of (Pet, Task) pairs.

- What classes did you include, and what responsibilities did you assign to each?
The design includes four classes, each with a distinct responsibility:
Task is responsible for representing a single to-do item — it holds the name, scheduled time, and completion status, and owns the logic to mark itself done via mark_done().
Pet is responsible for managing a collection of tasks belonging to a specific pet — it stores the pet's name and its task list, and controls membership through add_task() and remove_task().
Owner is responsible for managing a collection of pets — it stores the owner's name and their pet list, and controls membership through add_pet() and remove_pet().
Scheduler is responsible for querying and filtering the schedule — it takes an Owner as input and uses get_schedule(date_filter, include_done) to traverse the Owner → Pet → Task hierarchy, returning a filtered list of (Pet, Task) pairs.

**b. Design changes**

- Did your design change during implementation? Yes.
- If yes, describe at least one change and why you made it.

Added unique IDs to each dataclass,IDs avoid ambiguity when names are not unique.
id: str = field(default_factory=lambda: uuid4().hex) on Owner, Pet, Task.
---

## 2. Scheduling Logic and Tradeoffs

**a. Constraints and priorities**

- What constraints does your scheduler consider (for example: time, priority, preferences)?
- How did you decide which constraints mattered most?

**b. Tradeoffs**

- Describe one tradeoff your scheduler makes.
- Why is that tradeoff reasonable for this scenario?

---

## 3. AI Collaboration

**a. How you used AI**

- How did you use AI tools during this project (for example: design brainstorming, debugging, refactoring)?
- What kinds of prompts or questions were most helpful?

**b. Judgment and verification**

- Describe one moment where you did not accept an AI suggestion as-is.
- How did you evaluate or verify what the AI suggested?

---

## 4. Testing and Verification

**a. What you tested**

- What behaviors did you test?
- Why were these tests important?

**b. Confidence**

- How confident are you that your scheduler works correctly?
- What edge cases would you test next if you had more time?

---

## 5. Reflection

**a. What went well**

- What part of this project are you most satisfied with?

**b. What you would improve**

- If you had another iteration, what would you improve or redesign?

**c. Key takeaway**

- What is one important thing you learned about designing systems or working with AI on this project?
