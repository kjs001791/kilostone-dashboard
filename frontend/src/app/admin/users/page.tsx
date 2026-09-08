"use client";

import { useEffect, useState } from "react";
import { usersApi, User } from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import { useRouter } from "next/navigation";
import AppShell from "@/components/layout/AppShell";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useToast } from "@/hooks/use-toast";
import { Trash2, Pencil, UserPlus } from "lucide-react";

export default function UsersPage() {
  const { role, isLoading } = useAuth();
  const router = useRouter();
  const { toast } = useToast();

  const [users, setUsers] = useState<User[]>([]);
  const [createOpen, setCreateOpen] = useState(false);
  const [editTarget, setEditTarget] = useState<User | null>(null);

  const [form, setForm] = useState({ username: "", password: "", role: "driver" as "admin" | "driver" });
  const [editForm, setEditForm] = useState({ password: "", role: "driver" as "admin" | "driver", is_active: true });

  useEffect(() => {
    if (!isLoading && role !== "admin") router.replace("/dashboard");
  }, [isLoading, role, router]);

  useEffect(() => {
    if (role === "admin") loadUsers();
  }, [role]);

  async function loadUsers() {
    try {
      setUsers(await usersApi.list());
    } catch {
      toast({ title: "불러오기 실패", variant: "destructive" });
    }
  }

  async function handleCreate() {
    try {
      await usersApi.create(form);
      toast({ title: "계정 생성 완료" });
      setCreateOpen(false);
      setForm({ username: "", password: "", role: "driver" });
      loadUsers();
    } catch (e: any) {
      toast({ title: e.message ?? "생성 실패", variant: "destructive" });
    }
  }

  async function handleEdit() {
    if (!editTarget) return;
    const payload: any = { role: editForm.role, is_active: editForm.is_active };
    if (editForm.password) payload.password = editForm.password;
    try {
      await usersApi.update(editTarget.id, payload);
      toast({ title: "계정 수정 완료" });
      setEditTarget(null);
      loadUsers();
    } catch (e: any) {
      toast({ title: e.message ?? "수정 실패", variant: "destructive" });
    }
  }

  async function handleDelete(user: User) {
    if (!confirm(`'${user.username}' 계정을 삭제하시겠습니까?`)) return;
    try {
      await usersApi.delete(user.id);
      toast({ title: "계정 삭제 완료" });
      loadUsers();
    } catch (e: any) {
      toast({ title: e.message ?? "삭제 실패", variant: "destructive" });
    }
  }

  if (isLoading || role !== "admin") return null;

  return (
    <AppShell>
      <div className="p-6 max-w-2xl mx-auto">
        <div className="flex items-center justify-between mb-6">
          <h1 className="text-2xl font-bold">계정 관리</h1>
          <Button onClick={() => setCreateOpen(true)}>
            <UserPlus className="w-4 h-4 mr-2" /> 계정 추가
          </Button>
        </div>

        <Card>
          <CardContent className="p-0">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-muted-foreground">
                  <th className="text-left p-4">아이디</th>
                  <th className="text-left p-4">권한</th>
                  <th className="text-left p-4">상태</th>
                  <th className="text-left p-4">가입일</th>
                  <th className="p-4" />
                </tr>
              </thead>
              <tbody>
                {users.map((u) => (
                  <tr key={u.id} className="border-b last:border-0 hover:bg-muted/30">
                    <td className="p-4 font-medium">{u.username}</td>
                    <td className="p-4">
                      <Badge variant={u.role === "admin" ? "default" : "secondary"}>
                        {u.role === "admin" ? "관리자" : "운전자"}
                      </Badge>
                    </td>
                    <td className="p-4">
                      <Badge variant={u.is_active ? "outline" : "destructive"}>
                        {u.is_active ? "활성" : "비활성"}
                      </Badge>
                    </td>
                    <td className="p-4 text-muted-foreground">
                      {new Date(u.created_at).toLocaleDateString("ko-KR")}
                    </td>
                    <td className="p-4">
                      <div className="flex gap-2 justify-end">
                        <Button size="icon" variant="ghost" onClick={() => {
                          setEditTarget(u);
                          setEditForm({ password: "", role: u.role, is_active: u.is_active });
                        }}>
                          <Pencil className="w-4 h-4" />
                        </Button>
                        <Button size="icon" variant="ghost" className="text-destructive" onClick={() => handleDelete(u)}>
                          <Trash2 className="w-4 h-4" />
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </CardContent>
        </Card>
      </div>

      {/* 계정 추가 모달 */}
      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent>
          <DialogHeader><DialogTitle>계정 추가</DialogTitle></DialogHeader>
          <div className="space-y-4">
            <div className="space-y-1">
              <Label>아이디</Label>
              <Input value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} />
            </div>
            <div className="space-y-1">
              <Label>비밀번호</Label>
              <Input type="password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} />
            </div>
            <div className="space-y-1">
              <Label>권한</Label>
              <Select value={form.role} onValueChange={(v) => setForm({ ...form, role: v as any })}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="driver">운전자</SelectItem>
                  <SelectItem value="admin">관리자</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setCreateOpen(false)}>취소</Button>
            <Button onClick={handleCreate}>생성</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* 계정 수정 모달 */}
      <Dialog open={!!editTarget} onOpenChange={(o) => !o && setEditTarget(null)}>
        <DialogContent>
          <DialogHeader><DialogTitle>{editTarget?.username} 수정</DialogTitle></DialogHeader>
          <div className="space-y-4">
            <div className="space-y-1">
              <Label>새 비밀번호 (변경 시에만)</Label>
              <Input type="password" value={editForm.password} onChange={(e) => setEditForm({ ...editForm, password: e.target.value })} />
            </div>
            <div className="space-y-1">
              <Label>권한</Label>
              <Select value={editForm.role} onValueChange={(v) => setEditForm({ ...editForm, role: v as any })}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="driver">운전자</SelectItem>
                  <SelectItem value="admin">관리자</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <Label>상태</Label>
              <Select value={editForm.is_active ? "active" : "inactive"} onValueChange={(v) => setEditForm({ ...editForm, is_active: v === "active" })}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="active">활성</SelectItem>
                  <SelectItem value="inactive">비활성</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditTarget(null)}>취소</Button>
            <Button onClick={handleEdit}>저장</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </AppShell>
  );
}
