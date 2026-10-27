# Writing Visual Paradigm `.vpp` files directly: class model and class diagram

This reference comes from a real edit of `zamawianie-jedzenia.vpp`, a project from the desktop Community Edition with `PROJECT_BUILD` 20260914 and `DB_VERSION` 20121026. It was also cross-checked against 8 public `.vpp` files from VP builds 2014–2019. All of them have the same `DB_VERSION` and use the same format.

Scripts, in `vpp-edit/` (one-off scripts from the original lab work; not in this repo — their logic now lives in `vpp_mcp/`):

| Script | What it does |
|---|---|
| `edit_vpp.py` | Rebuilds the edited copy from `original.vpp` every time it runs, so the result is reproducible. Every text replacement on an existing definition must match exactly once, or the script aborts. |
| `verify_vpp.py` | Structural checker. Usage: `python3 -I verify_vpp.py file.vpp`. Exit code 0 means OK. |
| `model_vs_puml.py`, `members_vs_puml.py` | Read relationships and members back out of the database and compare them with a PlantUML class diagram. |

Outcome as reported by the coordinator (I did not observe it myself): the user's VP 2026 opened the edited copy, re-saved it, and the class diagram looked right. Only the connector line layout needed tidying.

---

## 1. Container format

A `.vpp` file is a plain SQLite 3 database. Use Python's `sqlite3` with `python3 -I`.

- **Integrity:** there are no checksums, hashes, signatures or ID counters anywhere. `PRAGMA integrity_check` must stay `ok`.
- **File header:** the header stays at schema format 4, UTF-8, with legacy read/write versions 1/1. Python's sqlite does not change these as long as you don't switch to WAL.
- **Do not VACUUM:** it isn't needed. Keep page layout changes minimal.
- **Never edit the user's original:** copy it to a pristine read-only backup, then work on a second copy.

### Tables

| Table | Columns that matter | Notes |
|---|---|---|
| `PROJECT_INFO` (1 row) | `ID`, `NAME`, `DEFINITION` (blob, project options), `ROOT_MODEL_ELEMENTS_DEFINITION` (text), `DIAGRAMS_DEFINITION` (text) | Update `ROOT_MODEL_ELEMENTS_DEFINITION` when you add a root model element, i.e. a row with `PARENT_ID` NULL such as a Stereotype or a Class. Update `DIAGRAMS_DEFINITION` only when you add a diagram. Leave `DEFINITION` alone. |
| `MODEL_ELEMENT` | `ID`, `USER_ID`, `USER_ID_PARENT`, `MODEL_TYPE`, `PARENT_ID`, `NAME`, `DEFINITION` (blob, UTF-8), `MIRROR_SOURCE`, `AUTHOR`, `CREATE_AT`, `LAST_MOD_AT` (seconds) | One row per top-level model element. Attributes, operations, parameters, association ends, qualifiers, enum literals and ModelViews are nested inside the owner's DEFINITION. They have no rows of their own. |
| `DIAGRAM` | `ID`, `DIAGRAM_TYPE` (`ClassDiagram`, `UseCaseDiagram`, `InteractionDiagram`, ...), `PARENT_MODEL_ID`, `NAME`, `DEFINITION` | The definition holds diagram options and the `Child=( ... )` list of every diagram element. |
| `DIAGRAM_ELEMENT` | `ID`, `SHAPE_TYPE`, `DIAGRAM_ID`, `MODEL_ELEMENT_ID`, `COMPOSITE_MODEL_ELEMENT_ADDRESS` (NULL), `REF_MODEL_ELEMENT_ADDRESS` (NULL), `PARENT_ID` (parent shape for nested shapes; NULL otherwise), `DEFINITION` | One row per shape **and** per connector. |
| `PROJECT_FILE` | `PATH`, `CONTENT` (gzip), `STATUS` (`'c'`) | Caches and option XML. Leave alone (see section 9). |
| `USER_ID_FORMAT` | `MODEL_TYPE`, `PREFIX`, `DIGITS`, `LAST_NUMERIC_VALUE` | Holds the user-visible IDs such as AC01 and UC13, for Actor, UseCase, Requirement and similar types. Classes and relationships don't use it. Only bump `LAST_NUMERIC_VALUE` if you add Actors or UseCases with `USER_ID`. |
| `TW_HISTORY`, `sqlite_sequence` | | Teamwork history, empty here. Leave alone. |

`MODEL_ELEMENT` column values for new rows:
- `USER_ID`, `USER_ID_PARENT` and `MIRROR_SOURCE` are NULL.
- `AUTHOR` is the project's author. It was `user` here; copy it from existing rows.
- `CREATE_AT` and `LAST_MOD_AT` are Unix seconds.
- `NAME` is the element name, or NULL for unnamed relationships. Relationship folders are named after their type, e.g. `'Association'`.

---

## 2. DEFINITION syntax

The format is VP's own text serialization, stored as a UTF-8 blob.

```
<ID>:<NAME>:<Type> {
	key=value;
	key=value;
}
```

**Header**
- `NAME` is `NULL` or a double-quoted string, e.g. `"Użytkownik"`. Write Polish letters as raw UTF-8.
- The header ID must equal the row's `ID` column.
- The header type must equal `MODEL_TYPE` or `SHAPE_TYPE` for that row.
- Every top-level definition ends with `;\n}` and has no trailing newline.

**Indentation and separators**
- One tab per nesting level. VP writes this style consistently; copy it exactly.
- Each entry is `key=value;` on its own line. Key order doesn't matter, and VP writes keys in arbitrary order.

**Value kinds**

| Kind | Form | Notes |
|---|---|---|
| Boolean | `T` / `F` | |
| Null | `NULL` | |
| Integer | `71`, `-117` | |
| Long timestamp | `lastModifiedTime=1792150000280;` | Milliseconds. |
| String | `"..."` | Escape `\"`. May contain raw newlines (HTML descriptions do). Some timestamps are stored as strings, e.g. `pmCreateDateTime="1792150000280"`. |
| Reference | `<ID>` | |
| Path reference | `<rootID:childID:grandchildID>` | Path of row IDs from the root, following `PARENT_ID`. |
| Nested sub-object reference | `<rowPath$nestedID>` or `<rowPath$nested$nested>` | e.g. `<H9ZMBIWFYFAUBBNZ:H9ZMBIWFYFAUBBNa:cEeMBIWFYFAUBBMj$KEeMBIWFYFAUBBMl>` points at an association end inside an association. |
| List | `(\n\t\titem, \n\t\titem\n\t)` | Items are separated by `", \n"` (comma, space, newline). |
| Nested object | `{ID:NAME:Type {\n ... \n}}` | Appears in lists or as a value, e.g. `from={...}`. |
| UI-model list | `_captionUIModel=(\n\t\t@x=0;, \n\t\t@y=0;, ...)` | Items look like `@key=value;` and are separated by `", "`. |

- **References to root elements** are bare `<ID>`: classes, data types, stereotypes, diagrams.
- **References to nested rows** use the full path: use cases under a System, relationships under containers. For example, a use case inside a System is `<SystemID:UseCaseID>`.
- **Diagram element references** are `<DiagramID:DiagramElementID>`. This form is used in `_fromShape`, `_toShape` and the diagram's `Child` list.
- **`Child=( ... )`** holds owned members as nested objects inside a class. In containers and diagrams it holds a list of path references.

---

## 3. IDs

- **Format:** 16 characters from `[A-Za-z0-9._]`, a 64-character alphabet.
- **What VP generates:** IDs look like 4 varying chars + a session stem + 3 counter chars, e.g. `O.1YIoWFYFAUBAmH` or `cEeMBIWFYFAUBBMj`. VP doesn't validate this structure.
- **What I generated:** `4 random chars + 'IoWFYFAUC' + 3-char counter`, checked against a set of every existing ID.
- **Build that set from all of these sources:**
  - row IDs in `MODEL_ELEMENT`, `DIAGRAM` and `DIAGRAM_ELEMENT`;
  - every nested ID found with `re.findall(r'\{([A-Za-z0-9._]{16}):', definition)`.
- **Which objects need an ID:**
  - every row;
  - every nested object: Attribute, Operation, Parameter, AssociationEnd, Qualifier, ModelView;
  - every diagram element.
- **IDs don't need to be sequential.**
- **USER_ID / USER_ID_FORMAT:** not used for classes or relationships (NULL). Actors and use cases carry `USER_ID` (`'AC01'`, `'UC03'`) and `userID="UC03";` in their definition.

---

## 4. Class, Attribute, Operation, Parameter

### Class row

| Column / key | Value |
|---|---|
| `MODEL_TYPE` | `Class` |
| `PARENT_ID` | NULL (root level, listed in `ROOT_MODEL_ELEMENTS_DEFINITION`) |
| `NAME` | class name |

Top-level keys:
- `_masterViewId="<shapeID>"` and `_modelViews=( {ID:"View":ModelView { container=<diagramID>; view="<shapeID>"; }} )`
- `abstract=T` for abstract classes.
- Stereotypes: `stereotypes=( <stereotypeID> )`. Interfaces use the stereotype named `Interface` (baseType `Class`); enumerations use `enumeration` (baseType `Class`). Both are Stereotype rows.
- `Child=( members )`
- Relationship back-references: `FromSimpleRelationships`, `ToSimpleRelationships`, `FromEndRelationships`, `ToEndRelationships` (see sections 5–6).
- Bookkeeping: `pmAuthor`, `pmCreateDateTime`, `pmLastModified`, `lastModifiedTime`, `_modelEditable=T`.

A class with no members simply has no `Child` key. Add one before the closing `}`.

### Primitive DataType rows

These are root rows in this project. Look them up by `NAME` in other projects; the IDs differ per project.

| Type | ID here |
|---|---|
| boolean | `_gWUBIWFYFAUBA2G` |
| byte | `IQWUBIWFYFAUBA2H` |
| char | `oQWUBIWFYFAUBA2I` |
| double | `oQWUBIWFYFAUBA2J` |
| float | `oQWUBIWFYFAUBA2K` |
| int | `oQWUBIWFYFAUBA2L` |
| long | `YQWUBIWFYFAUBA2M` |
| short | `YQWUBIWFYFAUBA2N` |
| void | `YQWUBIWFYFAUBA2O` |
| string | `YQWUBIWFYFAUBA2P` (lowercase; unused, the model uses `type_string="String"` instead) |

### Type keys

- `type=<ID>` refers to a DataType or a Class.
- `type_string="String"` (also `"LocalDate"`, `"LocalDateTime"`, ...) is free text, used for types that aren't in the model.
- On operations the same pair is spelled `returnType=<ID>` / `returnType_string="String"`.
- Generic types such as `List<Restauracja>` are stored as `returnType_string="List"` plus a nested `templateTypeBindInfo={... bindedType_string="List"; details=( {TemplateTypeBindDetails { arguments={TemplateTypeBindInfo ...}}} )}`. I didn't write any; copy an existing one if needed.

### Visibility

Applies to attributes and operations.

| Code | Meaning |
|---|---|
| key absent | private (attribute default; renders `-`) |
| `71` | public (`+`); what VP writes on new operations |
| `66`, `67`, `68` | seen in samples; protected and package. Not verified which is which, so avoid them. |

On association ends, `visibility=65` always appears; it is the "unspecified" default. Copy it as is.

### Other member keys

- `scope=65` means static (`{static}`). Absent means instance.
- `abstract=T` on an operation makes it abstract.
- `multiplicity="0..1"` (or `"0..*"`) on an attribute.
- **Constructors** (e.g. `Zamowienie(klient, ...)`): an Operation named like the class, with no `returnType` key.

### Snippets

Attribute (taken from the file; `type=<int>` form):
```
		{H1BkIoWFYFAUBAvd:"id":Attribute {
			pmLastModified="1792144763647";
			pmAuthor="user";
			type=<oQWUBIWFYFAUBA2L>;
			pmCreateDateTime="1792144706296";
			_modelViews=NULL;
			lastModifiedTime=1792144710818;
			_modelEditable=T;
		}}
```

Attribute with a string type and a multiplicity:
```
		{ZBqyIoWFYFAUBBKK:"uwagi":Attribute {
			type_string="String";
			pmLastModified="1792147554451";
			pmAuthor="user";
			pmCreateDateTime="1792147281958";
			_modelViews=NULL;
			lastModifiedTime=1792147544443;
			multiplicity="0..1";
			_modelEditable=T;
		}}
```

Operation with parameters:
```
		{GcNkIoWFYFAUBAwC:"zaloguj":Operation {
			visibility=71;
			_modelEditable=T;
			pmAuthor="user";
			lastModifiedTime=1792144772476;
			pmCreateDateTime="1792144753560";
			_modelViews=NULL;
			returnType=<_gWUBIWFYFAUBA2G>;
			Child=(
				{LrDkIoWFYFAUBAwH:"email":Parameter {
					type_string="String";
					pmLastModified="1792144782509";
					pmAuthor="user";
					pmCreateDateTime="1792144772468";
					_modelViews=NULL;
					lastModifiedTime=1792144772471;
					_modelEditable=T;
				}}, 
				{7rDkIoWFYFAUBAwI:"haslo":Parameter {
					...same shape...
				}}
			);
			pmLastModified="1792144782509";
		}}
```

Operation with no parameters, abstract, string return:
```
		{SXbkIoWFYFAUBAwR:"getRola":Operation {
			visibility=71;
			_modelEditable=T;
			returnType_string="String";
			pmAuthor="user";
			lastModifiedTime=1792144867421;
			pmCreateDateTime="1792144797330";
			_modelViews=NULL;
			abstract=T;
			pmLastModified="1792144877386";
		}}
```

- **Static operation:** add `scope=65;` inside the operation.
- **Enum literal** (in an enumeration class's `Child`): `{3RwEIoWFYFAUBAqX:"ZLOZONE":EnumerationLiteral { ...; classifiers=( <enumClassID> ); ... }}`
- **Changing a signature:** replace the operation's `returnType` and its whole inner `Child=( ... )` block. New parameters get new IDs. Removed parameter IDs vanish; check that nothing references them first (nothing did here).

---

## 5. Association

### Where it lives

- **Row:** `MODEL_TYPE='Association'`, `NAME` NULL. A name, if any, goes in the header, e.g. `"- utilizadores"`.
- **Parent:** `PARENT_ID` is the `ModelRelationshipContainer` named `Association`.
- **Container chain:** that container's parent is the root container named `relationships`, a root row with `PARENT_ID` NULL. The root container is listed in `ROOT_MODEL_ELEMENTS_DEFINITION`.
- **Container `Child` lists:** add `<relRoot:assocContainer:assocID>` to the Association container's `Child` list.
- **Containers may be missing:** if a type's container doesn't exist yet (Generalization, Realization, Usage, Dependency, Include, Extend), create a `ModelRelationshipContainer` row named after the type, with `PARENT_ID` = relationships root. Add `<relRoot:newContainer>` to the root container's `Child` list.
- **Existing IDs here:** relationships root `H9ZMBIWFYFAUBBNZ`, Association container `H9ZMBIWFYFAUBBNa`.

### Ends

| End | Direction | PlantUML side | Back-reference on the end's class |
|---|---|---|---|
| `from={...}` | `Direction=0` | first class in `A -- B` | `FromEndRelationships=( <path$fromEndID> )` |
| `to={...}` | `Direction=1` | second class | `ToEndRelationships=( <path$toEndID> )` |

Each end holds:
- `type=<classID>` and `EndModelElement=<classID>`, always the same value.
- `visibility=65` and a `qualifier={ID:"":Qualifier {...}}`. Both are always present.
- **Role name:** the end's header name, `{endID:"adresy":AssociationEnd {`. Use `NULL` when there is no role.
- **Multiplicity:** `multiplicity="1..*"`. Omit the key when unspecified.
- **aggregationKind:** goes on the **whole** end, i.e. the end at the diamond.
  - `67` = composite (filled diamond, `*--`)
  - `66` = shared (hollow diamond, `o--`)
  - absent = none

  `67` and `66` are high confidence: the BPMN-metamodel sample uses only 67, and the `66` vs `67` split matched intent in the student samples.
- **navigable:** medium confidence. Inferred from samples and my recollection of VP's OpenAPI constants (`NAVIGABLE_NAVIGABLE=0`, `NAVIGABLE_NON_NAVIGABLE=1`, `NAVIGABLE_UNSPECIFIED=2`). VP omits the key when the value is 0.

  | Value | Meaning |
  |---|---|
  | absent | navigable (default; VP's own plain associations have no key on either end) |
  | `1` | non-navigable |
  | `2` | unspecified |

  How I encoded each PlantUML form:
  - plain `--`, composition and aggregation: no key on either end;
  - directed `A --> B`: `navigable=2` on the from end, no key on the to end.

  The user reported the diagram looked right, which suggests this is correct, but check the arrows in VP.

### Snippet

Association model row, composite `Klient "1" *-- "1..*\nadresy" Adres`:
```
w.5UIoWFYFAUCAA4:NULL:Association {
	_modelEditable=T;
	_masterViewId="dFSxIoWFYFAUCAA5";
	pmAuthor="user";
	lastModifiedTime=1792150000280;
	pmCreateDateTime="1792150000280";
	_modelViews=(
		{gLVBIoWFYFAUCAA.:"View":ModelView {
			container=<f1DIIoWFYFAUBAjo>;
			view="dFSxIoWFYFAUCAA5";
		}}
	);
	from={.51OIoWFYFAUCAA6:NULL:AssociationEnd {
		visibility=65;
		_modelEditable=T;
		pmAuthor="user";
		lastModifiedTime=1792150000287;
		pmCreateDateTime="1792150000287";
		_modelViews=NULL;
		qualifier={9digIoWFYFAUCAA7:"":Qualifier {
			pmAuthor="user";
			pmCreateDateTime="1792150000287";
			_modelViews=NULL;
			lastModifiedTime=1792150000287;
			_modelEditable=T;
		}};
		aggregationKind=67;
		type=<CLyYIoWFYFAUBAkU>;
		EndModelElement=<CLyYIoWFYFAUBAkU>;
		multiplicity="1";
		Direction=0;
	}};
	to={bxgJIoWFYFAUCAA8:"adresy":AssociationEnd {
		visibility=65;
		...same bookkeeping + qualifier...
		type=<ndjYIoWFYFAUBAm2>;
		EndModelElement=<ndjYIoWFYFAUBAm2>;
		multiplicity="1..*";
		Direction=1;
	}};
	pmLastModified="1792150000280";
}
```

Back-references on the two classes:
```
	FromEndRelationships=(
		<H9ZMBIWFYFAUBBNZ:H9ZMBIWFYFAUBBNa:w.5UIoWFYFAUCAA4$.51OIoWFYFAUCAA6>
	);
```
The Adres class gets the same under `ToEndRelationships`, pointing at the to-end ID. If the list key already exists, append to it with `", \n\t\t<ref>"`.

Optional on an end: `referencedAttribute=<classPath$attrID>`, which links the end to an owned attribute (seen in the BPMN sample). Not needed.

---

## 6. Generalization, Realization, Usage, Dependency (the "simple" relationships)

**Common structure:** `fromModel=<...>`, `toModel=<...>`, `_masterViewId`, `_modelViews`, and optionally `stereotypes=( <id> )`.

**Row placement:** `PARENT_ID` = the type's container. Add `<relRoot:container:relID>` to that container's `Child` list.

**Back-references:**
- the `fromModel` element gets `FromSimpleRelationships=( <relRoot:container:relID> )`;
- the `toModel` element gets `ToSimpleRelationships=( ... )`.

The same pattern is used by Include and Extend in use case diagrams.

### Direction semantics

Verified against sample class names.

| Type | `fromModel` | `toModel` |
|---|---|---|
| Generalization | superclass (general) | subclass (specific) |
| Realization | interface (supplier) | implementing class |
| Dependency / Usage | client | supplier (the `..>` arrow points to `to`) |

### Stereotypes

A stereotype is a root row: `MODEL_TYPE='Stereotype'`, `PARENT_ID` NULL. Add it to `ROOT_MODEL_ELEMENTS_DEFINITION`.

```
oSY7IoWFYFAUCAAS:"use":Stereotype {
	pmLastModified="1792150000161";
	pmAuthor="user";
	pmCreateDateTime="1792150000161";
	_modelViews=NULL;
	baseType="Usage";
	lastModifiedTime=1792150000161;
	_modelEditable=T;
}
```

- `baseType` names the metaclass the stereotype applies to: `Usage`, `Class`, `Include`, `Extend`, `Attribute`, `UseCase`, ...
- Reuse an existing stereotype with the same name and baseType if there is one.
- I used Usage + stereotype `use` for «use», and Usage + stereotype `create` for «create». Samples also contain `instantiate` with baseType Usage.
- `PROJECT_FILE` `stereotypeFormats/<id>` entries exist only for some stereotypes. They are not required.

### Snippet

Usage row (Generalization and Realization are identical minus `stereotypes`):
```
q56hIoWFYFAUCAAs:NULL:Usage {
	stereotypes=(
		<oSY7IoWFYFAUCAAS>
	);
	_modelEditable=T;
	toModel=<j264IoWFYFAUBAoi>;
	_masterViewId="HHR.IoWFYFAUCAAt";
	pmAuthor="user";
	lastModifiedTime=1792150000231;
	pmCreateDateTime="1792150000231";
	_modelViews=(
		{wQ2mIoWFYFAUCAAu:"View":ModelView {
			container=<f1DIIoWFYFAUBAjo>;
			view="HHR.IoWFYFAUCAAt";
		}}
	);
	fromModel=<zIHYIoWFYFAUBAna>;
	pmLastModified="1792150000231";
}
```

Container row:
```
YP8eIoWFYFAUCAAU:"Generalization":ModelRelationshipContainer {
	pmLastModified="1792150000259";
	pmAuthor="user";
	Child=(
		<H9ZMBIWFYFAUBBNZ:YP8eIoWFYFAUCAAU:7JcuIoWFYFAUCAAX>, 
		<H9ZMBIWFYFAUBBNZ:YP8eIoWFYFAUCAAU:OGh0IoWFYFAUCAAa>
	);
	pmCreateDateTime="1792150000259";
	_modelViews=NULL;
	lastModifiedTime=1792150000259;
	_modelEditable=T;
}
```

---

## 7. DIAGRAM and DIAGRAM_ELEMENT

### Model and view link each other

| Side | Fields |
|---|---|
| Model element | `_masterViewId="<diagramElementID>"` and `_modelViews=( {newID:"View":ModelView { container=<diagramID>; view="<diagramElementID>"; }} )`. Several views mean several ModelView entries; the master view is one of them. |
| Diagram element | `metaModelElement=<full path of the model element>`. Root class: `<classID>`. Association: `<relRoot:assocContainer:assocID>`. |
| DIAGRAM_ELEMENT row | `MODEL_ELEMENT_ID` = the model element's row ID. |
| Diagram | `Child=( <diagramID:elemID>, ... )` lists **every** diagram element, including nested shapes and connectors. `customizedSortDiagramElementIds` is optional; new connectors needn't be added to it. |

### Shape rows

`SHAPE_TYPE` values seen:
- class and use case diagrams: `Class`, `Actor`, `UseCase`, `System`, `Package`, `NOTE`;
- sequence diagrams: `InteractionLifeLine`, `InteractionActor`, `Activation`, `Message`, `CombinedFragment`, `InteractionOperand`, `Gate`, `InteractionOccurrence`.

Geometry and positioning:
- **Coordinates:** `x=`, `y=`, `width=`, `height=` in diagram pixels. Top-level shapes use absolute coordinates.
- **Nested shapes:** use cases inside a System have `PARENT_ID` = the System shape and coordinates relative to it.
- **Caption width:** the class caption `_captionUIModel=( @x=0;, @y=0;, @width=<same as width>;, @height=15; ... )`. Keep its `@width` in sync when resizing.
- **No auto-fit:** class diagram option `autoFitShapesSize=F`. VP does NOT grow shapes when you add members; resize them yourself.
  - Rows are about 15 px each.
  - Width needs about 5.7 px per character of the longest member line at Dialog 11pt.
  - Example: Ocena with 3 attributes and 1 operation went from 80×40 to 290×92.

### Connector rows

- **SHAPE_TYPE:** the relationship type: `Association`, `Generalization`, `Realization`, `Usage`, `Dependency`, `Include`, `Extend`.
- **Endpoints:** `_fromShape=<diagramID:shapeID>` and `_toShape=<diagramID:shapeID>`.
- **`_points="x1,y1;...;xn,yn;"`:**
  - the **first** point is relative to the from-shape's x,y;
  - the **last** point is relative to the to-shape's x,y;
  - intermediate points are relative to the from shape.
- **Bounding box:** `x,y,width,height` = bounding box of the points relative to the from shape, minus 50, with width and height plus 100. VP recalculates this; straight two-point lines are fine.
- **Routing:** `useFromShapeCenter=T` and `useToShapeCenter=T` let VP re-route to the shape centers. Lines I wrote straight crossed other classes, and the user only had to tidy the layout.

Association connector snippet (key set from VP 2026; multiplicity and role label rectangles are optional and VP computes them):
```
dFSxIoWFYFAUCAA5:NULL:Association {
	foreground=(
		0, 
		0, 
		0, 
		255
	);
	fromPinType=1;
	_points="252,162;104,0;";
	showUniqueMultiplicityConstraint=T;
	showStereotypes=T;
	toPinType=1;
	showToRoleName=T;
	useToShapeCenter=T;
	showFromRoleVisibility=T;
	creatorDiagramType="ClassDiagram";
	_fromShape=<f1DIIoWFYFAUBAjo:CLyYIoWFYFAUBAkT>;
	showOrderedMultiplicityConstraint=T;
	useFromShapeCenter=T;
	y=112;
	x=-273;
	metaModelElement=<H9ZMBIWFYFAUBBNZ:H9ZMBIWFYFAUBBNa:w.5UIoWFYFAUCAA4>;
	showToRoleVisibility=T;
	showToMultiplicity=T;
	showFromRoleName=T;
	0SwDr=F;
	height=684;
	width=575;
	background=(
		122, 
		207, 
		245, 
		255
	);
	_elementFont=(
		@name="Dialog";, 
		@color=(
			0, 
			0, 
			0, 
			255
		);, 
		@size=11;, 
		@style=0;
	);
	_captionUIModel=(
		@x=4;, 
		@y=446;, 
		@width=20;, 
		@height=0;, 
		@side=1;, 
		@visible=T;, 
		@internalWidth=-2147483648;, 
		@internalHeight=-2147483648;
	);
	_toShape=<f1DIIoWFYFAUBAjo:ndjYIoWFYFAUBAm1>;
	_lineModel=(
		@cap=0;, 
		@transparency=0;, 
		@weight=1.0;, 
		@color=(
			0, 
			0, 
			0, 
			255
		);, 
		@hasStroke=T;
	);
	showFromMultiplicity=T;
	showMultiplicityConstraints=F;
}
```

Simple-relationship connectors (Generalization, Realization, Usage) use the key set of VP 2026's Include connector:
- `background`, `width`, `toPinType=1`, `useToShapeCenter=T`, `_captionUIModel`, `_toShape`, `_elementFont`, `_points`, `metaModelElement`, `fromPinType=1`, `foreground`, `y`, `_fromShape`, `x`, `creatorDiagramType="ClassDiagram"`, `_lineModel`, `height`, `useFromShapeCenter=T`;
- for a stereotyped Usage, the caption width is about 40 and the height 14.

The class shape key set (copy an existing shape row and change the ID, `metaModelElement` and geometry) includes:
- `showOperationSignature=T`, `visibilityStyle=1`, `showAttributeType=1`, `showOperationType=1`;
- `connectToPoint=T`, `creatorDiagramType="ClassDiagram"`, `_fillColor`, `_captionUIModel`, `interfaceBall=F`;
- some obfuscated keys: `lShCmMl=F`, `mSwTpPts=T`, `wpMbs=F`, `kSwCsMbSt=T`. Copy them verbatim.

---

## 8. PROJECT_INFO

**`ROOT_MODEL_ELEMENTS_DEFINITION`**
- Text of the form `rootModelElements:"rootModelElements":rootModelElements { Child=( <id>, ... ); }`.
- Append each new root row: classes, stereotypes, data types, packages.
- Nested rows (relationships, containers other than `relationships`) are not listed.
- I appended before the final `\n\t);\n}`.

**`DIAGRAMS_DEFINITION`**
- Text of the form `rootDiagrams:"rootDiagrams":rootDiagrams { Child=( <diagramID>, ... ); }`.
- Update it only when adding a diagram.

**`DEFINITION` (project options, `uimodel` with open diagrams):** don't touch.

---

## 9. Caches, re-save behaviour

- **`PROJECT_FILE` caches** (gzipped):
  - `vpdiagramshapes/<diagramID>.vps/details.xml` is an SVG/G2D render cache of shapes; its regions cover shapes only, not connectors.
  - `diagramPreviewData/<id>` is a PNG thumbnail.

  I left both stale. Per the coordinator's report (I didn't see this myself), the user's VP 2026 opened the file and re-saved it without problems; VP is expected to regenerate them on save.
- **Other `PROJECT_FILE` entries:** option XML, `stereotypeFormats/*` and `HTMLStringProperties/*`. Don't touch them.
- **VP tolerates small imperfections:** public sample files had a few unresolved references and still worked. Don't rely on that; keep the output clean.
- **Advice for the user:** open the copy in VP, check it, then Save, so VP rewrites caches and canonicalises the file. Afterwards they tidy connector routing by hand or with VP's layout.

---

## 10. Pitfalls and uncertainties

| Area | Confidence | Notes |
|---|---|---|
| Navigability codes | medium | See section 5. Easy to fix in VP if wrong. |
| Visibility codes 66/67/68 | unknown | Unmapped. Only "absent = private" and "71 = public" are certain. |
| `aggregationKind` | high | Only on the whole end. 67 composite, 66 shared. |
| Path references | | Must be full paths for nested rows. A bare `<assocID>` in a class back-reference would be wrong. Association-end back-references need `$endID`. |
| Diagram `Child` | | Must list every diagram element, connectors included. |
| Model ↔ view consistency | | `MODEL_ELEMENT_ID`, `metaModelElement`, `_modelViews` and `_masterViewId` must all agree. |
| Shape sizes | | Not auto-fit (`autoFitShapesSize=F`); resize shapes after adding or lengthening members, and avoid overlapping neighbours. |
| Existing use case associations | | The 11 Association rows here were actor–use case links on the use case diagram, not orphans. Check what existing relationships belong to before reusing them. |
| Sequence diagrams | not attempted | Too complex to guess safely: Frame, InteractionLifeLine, Message, Activation, CombinedFragment and InteractionOperand rows plus geometry. Samples with these exist on GitHub (`mendess/SGT`, `peerawutgaga/VPP-Project`) if someone attempts it. |
| Timestamps | | Use ms values slightly after the file's latest `pmLastModified`. Also set `LAST_MOD_AT` (seconds) on changed rows. |
| Writing | | Don't write while VP has the file open; VP locks it. |

---

## 11. Verification checklist

All of these are implemented in `verify_vpp.py`.

1. `PRAGMA integrity_check` = ok, and `foreign_key_check` is empty.
2. Every DEFINITION:
   - tokenizes with string-aware balanced `{}` and `()`;
   - has a header ID equal to the row ID;
   - has a header type equal to the `MODEL_TYPE` / `SHAPE_TYPE` column.
3. Every `<ref>` segment (split on `:` and `$`) resolves to a row ID or a nested ID.
4. All 16-character IDs are unique across rows and nested objects.
5. Model ↔ view links are consistent both ways:
   - each DIAGRAM_ELEMENT's `MODEL_ELEMENT_ID` matches its `metaModelElement`;
   - that model element has a ModelView pointing back to the same diagram and element;
   - each ModelView has a matching DIAGRAM_ELEMENT;
   - each `_fromShape` / `_toShape` exists on the same diagram.
6. Each diagram's `Child` list equals the set of its DIAGRAM_ELEMENT rows.
7. Each container's `Child` list equals the set of rows with that `PARENT_ID`.
8. `ROOT_MODEL_ELEMENTS_DEFINITION` equals the set of rows with `PARENT_ID` NULL.
9. Back-references:
   - simple relationships appear in `FromSimpleRelationships` / `ToSimpleRelationships` of their from and to elements;
   - associations appear as `path$endID` in `FromEndRelationships` / `ToEndRelationships` of their end types.
10. Diff against the original: only the intended rows were added or changed.
11. Semantic read-back against the source design (`model_vs_puml.py`, `members_vs_puml.py`).
12. Run the checker on the original as well. It must pass, to prove the checker isn't too strict.

---

## 12. Reusable code in `edit_vpp.py`

| Function | Purpose |
|---|---|
| `new_id()` | Unique 16-character ID. Seed `USED` via `DB.__init__`, which scans all row and nested IDs. |
| `ts()` | Monotonic millisecond timestamps. |
| `attribute(name, ('ref', id) \| ('str', 'String'), mult=None)` | Attribute block. |
| `parameter(...)` | Parameter block. |
| `params_block(...)` | A parameter `Child=( ... )` block. |
| `operation(name, returnTypeID, params)` | Operation block (public). |
| `DB.me` / `set_me` / `de` / `set_de` / `insert_me` / `insert_de` | Row read, write and insert helpers with the correct columns. |
| `add_children(defn, blocks)` | Append members to the top-level `Child=( )`, creating it if absent. |
| `append_ref_list(defn, key, ref)` | Append a reference to a top-level list key, creating the key if absent. Used for back-references, diagram `Child` and container `Child`. |
| `touch_top(defn)` | Bump the top-level `pmLastModified`. |
| `set_shape_geom(db, shapeID, x=, y=, width=, height=)` | Resize or move a shape; keeps the caption width in sync. |
| `border_point`, `connector_geometry` | Straight-connector `_points` and bounding box. |
| `simple_connector`, `assoc_connector`, `model_view` | Connector and ModelView templates. |
| `simple_rel(kind, fromID, toID, stereotypeID)` | One call creates the row, connector, container entry and back-references. |
| `end(side, classID, mult, role, aggregation, navigable)` | AssociationEnd block. |
| `replace_once(s, old, new, what)` | Safe edit of existing text; aborts unless there is exactly one match. |
