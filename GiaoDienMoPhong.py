"""Chẩn đoán giao diện ngoại tuyến. Không dùng Windows API, không quét cửa sổ, không gửi phím/chuột."""
import json
import sys
import threading
import random
import time
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox
from PIL import Image, ImageTk
ROOT = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent))
CONFIG = Path.home() / 'AutoTrainMil4NV_MoPhong_config.json'
PATTERNS=['BB DD CC AA','DD CC DD CC','EE DD BB HH','AA BB DD CC','HH DD EE CC','GG AA FF BB','BB HH DD EE','CC GG AA FF','FF BB HH DD','EE CC GG AA','DD EE CC GG','AA FF BB HH','HH BB FF AA','CC EE DD HH','GG CC EE DD','BB DD EE CC','FF AA GG CC','DD HH BB FF','EE GG CC AA','AA CC DD BB']
SKILLS=[f'Skill {i}' for i in range(1,6)]
TIMED=SKILLS+['Bay chỗ khác (8)','Bơm Máu (9)','Bơm Mana (0)']

class Character:
    def __init__(self, app, index, parent, saved):
        self.app=app; self.index=index; self.running=threading.Event(); self.thread=None
        self.hwnds={}; self.checks={}; self.intervals={}
        self.sim=None; self.timer=None
        # Toàn bộ tùy chọn nằm ngay trong ô nhân vật, không mở cửa sổ phụ.
        self.frame=tk.LabelFrame(parent,text=f'NHÂN VẬT {index}',font=('Segoe UI',8,'bold'),
                                 bg='white',fg='#075bb7',padx=3,pady=1,bd=2,relief='groove',highlightthickness=2,highlightbackground='#00a72c')
        self.frame.grid(row=(index-1)//2,column=(index-1)%2,sticky='nsew',padx=2,pady=1)
        # Nút BẬT/TẮT AUTO luôn ở vị trí đầu tiên trong mỗi ô nhân vật.
        self.button=tk.Button(self.frame,text='▶ MÔ PHỎNG',command=self.toggle,bg='#078d28',fg='white',
                              activebackground='#0b9e34',activeforeground='white',font=('Segoe UI',9,'bold'),height=1)
        self.button.pack(fill='x',pady=(0,2))
        self.window=tk.StringVar(value=saved.get('window',''))
        self.combo=ttk.Combobox(self.frame,textvariable=self.window,state='readonly',width=15,
                                font=('Segoe UI',8))
        self.combo.pack(fill='x',pady=(0,1))
        for label,key in [('Bật lùa quái Cự Thú, Thiên Ngoại Ảo','move'),
                          ('Tìm Quái và Đi Cổ Mộ','find')]:
            self.checks[key]=tk.BooleanVar(value=saved.get(key,False))
        for label in ['Nhặt Đồ']+TIMED:
            self.checks[label]=tk.BooleanVar(value=saved.get('enabled',{}).get(label,label=='Nhặt Đồ'))
            if label in TIMED:
                default='180' if label.startswith('Bay') else '2'
                self.intervals[label]=tk.StringVar(value=str(saved.get('intervals',{}).get(label,default)))
        for label,key in [('Lùa quái Cự Thú / Thiên Ngoại Ảo','move'),
                          ('Tìm quái / Cổ Mộ','find')]:
            tk.Checkbutton(self.frame,text=label,variable=self.checks[key],bg='white',
                           fg='#9d2921',font=('Segoe UI',7,'bold'),anchor='w',
                           padx=0,pady=0).pack(fill='x')
        tk.Frame(self.frame,height=1,bg='#c4ddf4').pack(fill='x',pady=1)
        skills=tk.Frame(self.frame,bg='white');skills.pack(fill='x')
        skills.columnconfigure(0,weight=1)
        tk.Label(skills,text='Tính năng',bg='white',fg='#43698e',font=('Segoe UI',7,'bold')).grid(row=0,column=0,sticky='w')
        tk.Label(skills,text='Giây',bg='white',fg='#43698e',font=('Segoe UI',7,'bold')).grid(row=0,column=1)
        for ri,label in enumerate(['Nhặt Đồ']+TIMED,1):
            tk.Checkbutton(skills,text=label,variable=self.checks[label],bg='white',
                           font=('Segoe UI',7),anchor='w',padx=0,pady=0).grid(row=ri,column=0,sticky='w',pady=0)
            if label in TIMED:
                tk.Entry(skills,textvariable=self.intervals[label],width=6,
                         font=('Segoe UI',7),justify='center',relief='solid',bd=1).grid(row=ri,column=1,sticky='e',padx=(2,1),pady=0)
        self.status=tk.StringVar(value='Sẵn sàng (ngoại tuyến)')
        tk.Label(self.frame,textvariable=self.status,bg='white',fg='#44617a',
                 font=('Segoe UI',7,'bold'),wraplength=230,anchor='w').pack(fill='x',pady=(1,0))

    def refresh(self, options=None):
        self.hwnds = {}
        self.combo['values'] = ['Chế độ xem giao diện']
        self.window.set('Chế độ xem giao diện')

    def settings(self):
        return {'window':self.window.get(),'move':self.checks['move'].get(),
                'find':self.checks['find'].get(),
                'enabled':{k:v.get() for k,v in self.checks.items() if k not in ('move','find')},
                'intervals':{k:v.get() for k,v in self.intervals.items()}}

    def toggle(self):
        if self.sim is not None:
            self.stop()
            return
        try:
            intervals = {name: float(v.get().replace(',', '.')) for name, v in self.intervals.items()}
            if any(not (0.1 <= x <= 10800) for x in intervals.values()):
                raise ValueError()
        except ValueError:
            messagebox.showwarning('Thời gian không hợp lệ', 'Nhập thời gian từ 0,1 đến 10800 giây.')
            return
        self.app.save()
        flags = {name: v.get() for name, v in self.checks.items()}
        self.sim = {'flags': flags, 'intervals': intervals, 'route': '', 'i': 0,
                    'phase': 'moving' if flags['move'] else 'idle',
                    'start': time.monotonic(), 'next': time.monotonic(),
                    'fight_start': 0, 'f1': 0, 'return_at': time.monotonic()+300,
                    'return_step': 0, 'return_until': 0,
                    'last_skill': {}, 'count': 0}
        self._new_route()
        self.button.config(text='■ DỪNG MÔ PHỎNG', bg='#d44444')
        self._tick()

    def _new_route(self):
        if self.sim is None: return
        self.sim['route'] = ''.join(t[0]*2 for t in random.choice(PATTERNS).split()[:3])
        self.sim['i'] = 0

    def _tick(self):
        s = self.sim
        if s is None: return
        now = time.monotonic()
        if s['flags']['move'] and now >= s['return_at'] and s['phase'] not in ('return_click', 'return_wait', 'return_escape', 'return_pause'):
            s['phase']='return_click'; s['return_step']=0; s['next']=now
            self.status.set('Mô phỏng Alt+D (không gửi phím)')
        phase=s['phase']
        if phase == 'return_click' and now >= s['next']:
            s['return_step']+=1
            self.status.set(f'Mô phỏng nhấp trung tâm {s["return_step"]}/10')
            s['next']=now+0.25
            if s['return_step']>=10:
                s['phase']='return_wait'; s['return_until']=now+30
        elif phase == 'return_wait':
            self.status.set(f'Mô phỏng chờ trung tâm: {max(0,int(s["return_until"]-now))}s')
            if now>=s['return_until']:
                s['phase']='return_escape'; s['return_step']=0; s['next']=now
        elif phase == 'return_escape' and now>=s['next']:
            s['return_step']+=1
            self.status.set(f'Mô phỏng Esc {s["return_step"]}/2')
            s['next']=now+0.25
            if s['return_step']>=2:
                s['phase']='return_pause'; s['return_until']=now+2
        elif phase == 'return_pause' and now>=s['return_until']:
            self._new_route(); s['phase']='moving'; s['next']=now; s['return_at']=now+300
        elif phase == 'moving' and now>=s['next']:
            letter=s['route'][s['i']]; s['i']+=1; s['count']+=1
            self.status.set(f'Mô phỏng điểm {letter}: {s["i"]}/6 • lượt {s["count"]}')
            s['next']=now+random.choice((2,2.5,3))
            if s['i']>=len(s['route']):
                s['phase']='fighting'; s['fight_start']=now; s['f1']=0
        elif phase == 'fighting':
            elapsed=now-s['fight_start']
            if elapsed>=15:
                self._new_route(); s['phase']='moving'; s['next']=now
            elif s['f1']<6 and elapsed>=3+2*s['f1']:
                s['f1']+=1
                self.status.set(f'Mô phỏng F1 {s["f1"]}/6 • đứng 15s')
        elif phase == 'idle':
            self.status.set('Mô phỏng đang chạy • không chọn lùa quái')
        # Only show simulated events, never send OS input or inspect processes/windows.
        if s['phase'] not in ('return_click','return_wait','return_escape','return_pause'):
            for name, enabled in s['flags'].items():
                if not enabled or name in ('move','find','Nhặt Đồ'): continue
                period=s['intervals'].get(name, 2)
                if now-s['last_skill'].get(name, s['start']) >= period:
                    s['last_skill'][name]=now
        self.timer=self.app.root.after(100, self._tick)

    def stop(self):
        self.sim=None
        if self.timer is not None:
            try: self.app.root.after_cancel(self.timer)
            except tk.TclError: pass
            self.timer=None
        self.running.clear()
        self.button.config(text='▶ MÔ PHỎNG',bg='#078d28')
        self.status.set('Đã dừng mô phỏng')

    def report(self,msg):
        try:self.app.root.after(0,lambda:self.status.set(msg))
        except RuntimeError:pass

    def _ended(self):
        self.button.config(text='▶ MÔ PHỎNG',bg='#078d28')
        self.status.set('Đã dừng')

class App:
    def __init__(self):
        self.root=tk.Tk()
        self.root.title('Auto Train Mil và Cổ Mộ — Mô phỏng ngoại tuyến 4 NV')
        # Cố định tỷ lệ 9:16, 540x960px; không có cuộn dọc.
        # Skill 1-5, giao diện thu gọn.
        self.root.geometry('540x960')
        self.root.resizable(False,False)
        self.root.configure(bg='#e7f3ff')
        self.data={}
        try:self.data=json.loads(CONFIG.read_text(encoding='utf-8'))
        except (OSError,ValueError):pass
        self.characters=[]
        self.build()
        self.root.protocol('WM_DELETE_WINDOW',self.close)

    def build(self):
        # Nền cây xanh hoạt hình phủ toàn bộ cửa sổ, bao quanh bốn bảng chức năng.
        self.canvas=tk.Canvas(self.root,bg='#bdf5df',highlightthickness=0,bd=0)
        self.canvas.pack(side='left',fill='both',expand=True)
        bg_file=ROOT/'forest_background.png'
        self.bg_original=Image.open(bg_file).convert('RGB') if bg_file.exists() else None
        self.bg_photo=None
        self.bg_id=self.canvas.create_image(0,0,anchor='nw') if self.bg_original else None
        self.content=tk.Frame(self.canvas,bg='#d8f6e7')
        self.content_id=self.canvas.create_window(15,8,window=self.content,anchor='nw')
        self.canvas.bind('<Configure>',self._resize_background)

        # Banner hai nhân vật tràn toàn bộ bề ngang phần nội dung.
        banner=ROOT/'header.png'
        if banner.exists():
            im=Image.open(banner).convert('RGB')
            # Ảnh banner gốc đã có chữ vàng nổi, Zalo và hai nhân vật.
            # Không vẽ thêm chữ trắng che lên ảnh.
            self.banner_source=im
            self.banner_width=0
            b=tk.Canvas(self.content,width=535,height=112,highlightthickness=0,bd=0)
            b.pack(fill='x',padx=0,pady=(0,1))
            self.banner_canvas=b
            self.banner_image_id=b.create_image(0,0,anchor='nw')
            b.bind('<Configure>',self._resize_banner)
        else:
            tk.Label(self.content,text='Auto Train Mil và Cổ Mộ',font=('Segoe UI',14,'bold'),
                     bg='#0875d4',fg='white').pack(fill='x',ipady=6)
        toolbar=tk.Frame(self.content,bg='#d8f6e7');toolbar.pack(fill='x',padx=6,pady=(1,1))
        ttk.Button(toolbar,text='⟳ Làm mới',command=self.refresh_all).pack(side='left')
        tk.Label(toolbar,text='Zalo: TuanHo – 0398438721',font=('Segoe UI',8,'bold'),
                 bg='#d8f6e7',fg='#064d9b').pack(side='right',padx=3)
        grid=tk.Frame(self.content,bg='#d8f6e7');grid.pack(fill='both',expand=True,padx=3,pady=1)
        for c in range(2):grid.columnconfigure(c,weight=1,uniform='characters')
        for r in range(2):grid.rowconfigure(r,weight=1,uniform='characters')
        saved=self.data.get('characters',[{}]*4)
        for i in range(4):
            self.characters.append(Character(self,i+1,grid,saved[i] if i<len(saved) else {}))
        self.refresh_all()
        self.sync=tk.BooleanVar(value=False)


    def _resize_banner(self,event):
        width=max(1,event.width)
        if width==self.banner_width:return
        self.banner_width=width
        height=112  # Thu gọn banner để cả 4 trạng thái Sẵn sàng hiển thị
        self.banner_canvas.configure(height=height)
        self.banner=ImageTk.PhotoImage(self.banner_source.resize((width,height),Image.Resampling.LANCZOS))
        self.banner_canvas.itemconfigure(self.banner_image_id,image=self.banner)

    def _resize_background(self,event):
        if self.bg_original is not None:
            im=self.bg_original.resize((max(1,event.width),max(1,event.height)),Image.Resampling.LANCZOS)
            self.bg_photo=ImageTk.PhotoImage(im)
            self.canvas.itemconfig(self.bg_id,image=self.bg_photo)
            self.canvas.tag_lower(self.bg_id)
        # Giữ lá cây tràn viền, chừa 15px ở hai cạnh.
        self.canvas.itemconfig(self.content_id,width=max(480,event.width-20))

    def refresh_all(self):
        for c in self.characters:c.refresh()

    def sync_settings(self):
        if not self.sync.get():return
        src=self.characters[0]
        for dst in self.characters[1:]:
            for name,var in src.checks.items():dst.checks[name].set(var.get())
            for name,var in src.intervals.items():dst.intervals[name].set(var.get())
        self.save()

    def start_all(self):
        for c in self.characters:
            if not c.running.is_set():c.toggle()

    def stop_all(self):
        for c in self.characters:c.stop()

    def save(self):
        data={'characters':[c.settings() for c in self.characters], 'sync':self.sync.get() if hasattr(self,'sync') else False}
        try:CONFIG.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
        except OSError:pass

    def close(self):
        self.stop_all();self.save();self.root.destroy()

if __name__=='__main__':
    App().root.mainloop()
