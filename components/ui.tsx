"use client";
import { ReactNode } from "react";
import { X } from "lucide-react";

export function Card({ children, className="" }: { children: ReactNode; className?: string }) { return <section className={`card ${className}`}>{children}</section>; }
export function Badge({ children, tone="neutral" }: { children: ReactNode; tone?: string }) { return <span className={`badge ${tone}`}>{children}</span>; }
export function Progress({ value, color="blue" }: { value: number; color?: string }) { return <div className="progress-track"><div className={`progress-fill ${color}`} style={{width:`${Math.max(0,Math.min(100,value))}%`}} /></div>; }
export function Empty({ title, text }: { title: string; text: string }) { return <div className="empty"><div className="empty-mark">◇</div><h3>{title}</h3><p>{text}</p></div>; }
export function Modal({ title, children, onClose, wide=false }: { title:string; children:ReactNode; onClose:()=>void; wide?:boolean }) { return <div className="modal-backdrop" onMouseDown={onClose}><div className={`modal ${wide?"wide":""}`} onMouseDown={e=>e.stopPropagation()}><header><div><span className="eyebrow">Add record</span><h2>{title}</h2></div><button className="icon-btn" onClick={onClose} aria-label="Close"><X size={20}/></button></header>{children}</div></div>; }
export function Field({ label, children, span=false }: { label:string; children:ReactNode; span?:boolean }) { return <label className={span?"field span":"field"}><span>{label}</span>{children}</label>; }
export function SectionTitle({ eyebrow, title, action }: { eyebrow?:string; title:string; action?:ReactNode }) { return <div className="section-title"><div>{eyebrow&&<span className="eyebrow">{eyebrow}</span>}<h2>{title}</h2></div>{action}</div>; }
