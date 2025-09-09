import React from 'react';

export default function PitcherTable({ pitchers }: { pitchers: Array<any> }) {
  if (!pitchers || pitchers.length === 0) return <p className="small">投手成績なし</p>;
  return (
    <table style={{width:'100%', borderCollapse:'collapse', fontSize:13}}>
      <thead>
        <tr>
          <th style={{textAlign:'left'}}>投手/捕手</th>
          <th>SO</th>
          <th>BB</th>
          <th>H</th>
          <th>HR</th>
          <th>WP</th>
          <th>BK</th>
          <th>PB</th>
        </tr>
      </thead>
      <tbody>
        {pitchers.map((p) => (
          <tr key={p.name}>
            <td>{p.name}</td>
            <td style={{textAlign:'right'}}>{p.SO ?? 0}</td>
            <td style={{textAlign:'right'}}>{p.BB ?? 0}</td>
            <td style={{textAlign:'right'}}>{p.H ?? 0}</td>
            <td style={{textAlign:'right'}}>{p.HR ?? 0}</td>
            <td style={{textAlign:'right'}}>{p.WP ?? 0}</td>
            <td style={{textAlign:'right'}}>{p.BK ?? 0}</td>
            <td style={{textAlign:'right'}}>{p.PB ?? 0}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
