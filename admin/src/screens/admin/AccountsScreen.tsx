import { listAccounts, listDoctors } from "../../api/client";
import type { StaffUser } from "../../api/types";
import { AccountRow } from "../../components/AccountRow";
import { CreateAccountForm } from "../../components/CreateAccountForm";
import { Loadable } from "../../components/Loadable";
import { PageHeader } from "../../components/PageHeader";
import { useApi } from "../../lib/useApi";

export function AccountsScreen({ currentUser }: { currentUser: StaffUser }) {
  const accounts = useApi(listAccounts, "accounts");
  const doctors = useApi(listDoctors, "doctors");

  const updated = (user: StaffUser) => {
    accounts.replace((accounts.data ?? []).map((u) => (u.id === user.id ? user : u)));
    doctors.reload();
  };

  const created = () => {
    accounts.reload();
    doctors.reload();
  };

  return (
    <>
      <PageHeader title="Accounts" />
      <section className="card" aria-labelledby="create-login-heading">
        <h2 id="create-login-heading">Create doctor login</h2>
        <Loadable state={doctors}>
          {(list) => (
            <CreateAccountForm
              doctors={list.filter((doctor) => doctor.account === null)}
              onCreated={created}
            />
          )}
        </Loadable>
      </section>
      <h2 className="section-title">Staff logins</h2>
      <Loadable state={accounts}>
        {(users) => (
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th scope="col">Name</th>
                  <th scope="col">Email</th>
                  <th scope="col">Role</th>
                  <th scope="col">Doctor</th>
                  <th scope="col">Status</th>
                  <th scope="col">Last login</th>
                  <th scope="col">
                    <span className="sr-only">Actions</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {users.map((user) => (
                  <AccountRow
                    key={user.id}
                    user={user}
                    isCurrentUser={user.id === currentUser.id}
                    onUpdated={updated}
                  />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Loadable>
    </>
  );
}
