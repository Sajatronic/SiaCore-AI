export default function ComponentList({ names }) {
  return (
    <ul className="component-list" onClick={(event) => event.stopPropagation()}>
      {names.map((name) => (
        <li key={name} className="component-bullet">
          {name}
        </li>
      ))}
    </ul>
  );
}
